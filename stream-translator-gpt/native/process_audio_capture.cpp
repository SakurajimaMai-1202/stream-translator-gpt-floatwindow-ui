#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <audioclientactivationparams.h>
#include <wrl.h>
#include <atomic>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>
#include <algorithm>
#include <chrono>
using namespace Microsoft::WRL;

// Callback has its own lifetime: late activation cannot access a destroyed capture.
class Activation final : public RuntimeClass<RuntimeClassFlags<ClassicCom>,
    IActivateAudioInterfaceCompletionHandler, FtmBase> {
public:
    HANDLE event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    HRESULT result = E_PENDING;
    ComPtr<IAudioClient> client;
    ~Activation() { if (event) CloseHandle(event); }
    STDMETHOD(ActivateCompleted)(IActivateAudioInterfaceAsyncOperation* operation) override {
        HRESULT activated = E_FAIL;
        ComPtr<IUnknown> object;
        result = operation->GetActivateResult(&activated, &object);
        if (SUCCEEDED(result)) result = activated;
        if (SUCCEEDED(result)) result = object.As(&client);
        SetEvent(event);
        return S_OK;
    }
};
struct Capture {
    HANDLE process = nullptr;
    HANDLE stop = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    HANDLE ready = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    HANDLE done = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    DWORD pid;
    std::atomic<HRESULT> status{S_OK};
    std::atomic<uint64_t> dropped{0};
    std::mutex mutex;
    std::condition_variable available;
    std::vector<float> ring = std::vector<float>(48000 * 2 * 5);
    size_t head = 0, count = 0;
    std::atomic<bool> started{false}, stopped{false};
    ~Capture() { if(process) CloseHandle(process); if(stop) CloseHandle(stop); if(ready) CloseHandle(ready); if(done) CloseHandle(done); }
    void fail(HRESULT hr) { status = hr; available.notify_all(); }
    void push(const float* data, UINT32 frames, bool silent, bool gap) {
        std::lock_guard<std::mutex> lock(mutex);
        if(gap) { dropped += count / 2 + 1; head = count = 0; }
        size_t n = size_t(frames) * 2;
        if(n > ring.size()) { dropped += (n - ring.size()) / 2; if(!silent) data += n-ring.size(); n=ring.size(); }
        if(count+n > ring.size()) { size_t discard=count+n-ring.size(); head=(head+discard)%ring.size(); count-=discard; dropped+=discard/2; }
        for(size_t i=0;i<n;++i) ring[(head+count+i)%ring.size()] = silent ? 0.0f : data[i];
        count += n;
        available.notify_all();
    }
};
struct Handle { std::shared_ptr<Capture> state; };
static void worker(std::shared_ptr<Capture> state) {
    HRESULT com = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    HRESULT hr = com;
    ComPtr<IAudioClient> client;
    ComPtr<IAudioCaptureClient> capture;
    HANDLE audio = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    bool running = false;
    do {
        if(FAILED(hr)) break;
        if(!audio) { hr=HRESULT_FROM_WIN32(GetLastError()); break; }
        auto callback = Make<Activation>();
        if(!callback || !callback->event) { hr=E_OUTOFMEMORY; break; }
        AUDIOCLIENT_ACTIVATION_PARAMS params{};
        params.ActivationType=AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK;
        params.ProcessLoopbackParams.TargetProcessId=state->pid;
        params.ProcessLoopbackParams.ProcessLoopbackMode=PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE;
        PROPVARIANT prop{}; prop.vt=VT_BLOB; prop.blob.cbSize=sizeof(params); prop.blob.pBlobData=reinterpret_cast<BYTE*>(&params);
        ComPtr<IActivateAudioInterfaceAsyncOperation> operation;
        hr=ActivateAudioInterfaceAsync(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK, __uuidof(IAudioClient), &prop, callback.Get(), &operation);
        if(FAILED(hr)) break;
        HANDLE activationEvents[]={state->stop,callback->event,state->process};
        DWORD wait=WaitForMultipleObjects(3,activationEvents,FALSE,10000);
        if(wait!=WAIT_OBJECT_0+1) { hr=HRESULT_FROM_WIN32(wait==WAIT_TIMEOUT?ERROR_TIMEOUT:(wait==WAIT_OBJECT_0+2?ERROR_PROCESS_ABORTED:ERROR_CANCELLED)); break; }
        hr=callback->result; if(FAILED(hr)) break;
        client=callback->client;
        WAVEFORMATEX format{};
        format.wFormatTag=WAVE_FORMAT_IEEE_FLOAT; format.nChannels=2; format.nSamplesPerSec=48000;
        format.wBitsPerSample=32; format.nBlockAlign=8; format.nAvgBytesPerSec=384000;
        hr=client->Initialize(AUDCLNT_SHAREMODE_SHARED, AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,0,0,&format,nullptr);
        if(FAILED(hr)) break;
        hr=client->GetService(IID_PPV_ARGS(&capture)); if(FAILED(hr)) break;
        hr=client->SetEventHandle(audio); if(FAILED(hr)) break;
        hr=client->Start(); if(FAILED(hr)) break;
        running=true;
        SetEvent(state->ready);
        HANDLE events[]={state->stop,state->process,audio};
        while(true) {
            DWORD event=WaitForMultipleObjects(3,events,FALSE,250);
            if(event==WAIT_OBJECT_0) break;
            if(event==WAIT_OBJECT_0+1) { hr=HRESULT_FROM_WIN32(ERROR_PROCESS_ABORTED); break; }
            if(event==WAIT_FAILED) { hr=HRESULT_FROM_WIN32(GetLastError()); break; }
            UINT32 packet=0;
            hr=capture->GetNextPacketSize(&packet);
            while(SUCCEEDED(hr) && packet && WaitForSingleObject(state->stop,0)!=WAIT_OBJECT_0) {
                BYTE* data=nullptr; UINT32 frames=0; DWORD flags=0;
                hr=capture->GetBuffer(&data,&frames,&flags,nullptr,nullptr);
                if(FAILED(hr)) break;
                state->push(reinterpret_cast<float*>(data),frames,(flags&AUDCLNT_BUFFERFLAGS_SILENT)!=0,(flags&AUDCLNT_BUFFERFLAGS_DATA_DISCONTINUITY)!=0);
                hr=capture->ReleaseBuffer(frames);
                if(SUCCEEDED(hr)) hr=capture->GetNextPacketSize(&packet);
            }
            if(FAILED(hr)) break;
        }
    } while(false);
    if(FAILED(hr) && WaitForSingleObject(state->stop,0)!=WAIT_OBJECT_0) state->fail(hr);
    if(running) client->Stop();
    capture.Reset(); client.Reset();
    if(audio) CloseHandle(audio);
    if(SUCCEEDED(com)) CoUninitialize();
    state->stopped=true;
    SetEvent(state->ready); SetEvent(state->done); state->available.notify_all();
}
#define API extern "C" __declspec(dllexport)
API void* pa_create(uint32_t pid, uint64_t expected_creation_time, int* error) {
    if(error) *error=0;
    try {
        auto state=std::make_shared<Capture>(); state->pid=pid;
        state->process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,pid);
        HRESULT hr=S_OK;
        if(!state->process) hr=HRESULT_FROM_WIN32(GetLastError());
        else {
            FILETIME creation{},exit{},kernel{},user{};
            if(!GetProcessTimes(state->process,&creation,&exit,&kernel,&user)) hr=HRESULT_FROM_WIN32(GetLastError());
            else if(expected_creation_time && expected_creation_time!=((uint64_t(creation.dwHighDateTime)<<32)|creation.dwLowDateTime)) hr=HRESULT_FROM_WIN32(ERROR_INVALID_DATA);
            else if(WaitForSingleObject(state->process,0)==WAIT_OBJECT_0) hr=HRESULT_FROM_WIN32(ERROR_PROCESS_ABORTED);
        }
        if(!state->stop || !state->ready || !state->done) hr=E_OUTOFMEMORY;
        if(FAILED(hr)) { if(error) *error=hr; return nullptr; }
        return new Handle{state};
    } catch(...) { if(error) *error=E_OUTOFMEMORY; return nullptr; }
}
API int pa_start(void* raw) {
    if(!raw) return E_POINTER;
    auto state=static_cast<Handle*>(raw)->state;
    if(state->stopped) return HRESULT_FROM_WIN32(ERROR_CANCELLED);
    if(state->started.exchange(true)) return HRESULT_FROM_WIN32(ERROR_INVALID_STATE);
    try { std::thread(worker,state).detach(); } catch(...) { state->fail(E_OUTOFMEMORY); state->stopped=true; SetEvent(state->done); return E_OUTOFMEMORY; }
    if(WaitForSingleObject(state->ready,12000)!=WAIT_OBJECT_0) { state->fail(HRESULT_FROM_WIN32(ERROR_TIMEOUT)); SetEvent(state->stop); return state->status; }
    if(state->stopped && SUCCEEDED(state->status.load())) return HRESULT_FROM_WIN32(ERROR_CANCELLED);
    return state->status;
}
API int pa_read(void* raw,float* out,int capacity,int timeout_ms) {
    if(!raw || !out || capacity<2 || timeout_ms<0) return E_INVALIDARG;
    auto state=static_cast<Handle*>(raw)->state;
    std::unique_lock<std::mutex> lock(state->mutex);
    state->available.wait_for(lock,std::chrono::milliseconds(timeout_ms),[&]{return state->count || state->stopped || FAILED(state->status.load());});
    if(FAILED(state->status.load())) return state->status;
    size_t n=std::min(state->count,size_t(capacity&~1));
    for(size_t i=0;i<n;++i) out[i]=state->ring[(state->head+i)%state->ring.size()];
    state->head=(state->head+n)%state->ring.size(); state->count-=n;
    return int(n);
}
API int pa_status(void* raw) { return raw?static_cast<Handle*>(raw)->state->status.load():E_POINTER; }
API uint64_t pa_dropped_frames(void* raw) { return raw?static_cast<Handle*>(raw)->state->dropped.load():0; }
API void pa_stop(void* raw) {
    if(!raw) return;
    auto state=static_cast<Handle*>(raw)->state;
    SetEvent(state->stop); state->stopped=true; state->available.notify_all();
    if(state->started) WaitForSingleObject(state->done,5000);
}
API void pa_destroy(void* raw) { if(raw) { pa_stop(raw); delete static_cast<Handle*>(raw); } }
