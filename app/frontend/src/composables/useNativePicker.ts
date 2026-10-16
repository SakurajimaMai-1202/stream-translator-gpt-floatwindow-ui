import { onBeforeUnmount, onMounted, ref } from 'vue';

type PickerBridge = {
  chooseFolder?: (title: string, startDir: string, callback: (path: string) => void) => void;
  chooseFile?: (title: string, startDir: string, filter: string, callback: (path: string) => void) => void;
};

export function useNativePicker() {
  const available = ref(false);
  const getBridge = () => (window as Window & { pyqt?: PickerBridge }).pyqt;
  let bridgeProbe: ReturnType<typeof setInterval> | undefined;
  onMounted(() => {
    let attempts = 0;
    const probe = () => {
      const bridge = getBridge();
      available.value = typeof bridge?.chooseFolder === 'function' && typeof bridge?.chooseFile === 'function';
      // A slow first launch can expose the bridge well after mount.
      if (available.value || ++attempts >= 120) clearInterval(bridgeProbe);
    };
    bridgeProbe = setInterval(probe, 250);
    probe();
  });
  onBeforeUnmount(() => clearInterval(bridgeProbe));

  // Qt queues a second modal dialog on a double click; ignore clicks while one is open.
  let picking = false;
  function guarded(open: (resolve: (path: string | null) => void) => void): Promise<string | null> {
    if (picking) return Promise.resolve(null);
    picking = true;
    return new Promise<string | null>(open).finally(() => { picking = false; });
  }
  function pickFolder(title: string, startDir = ''): Promise<string | null> {
    return guarded(resolve => {
      const bridge = getBridge();
      if (!bridge?.chooseFolder) { resolve(null); return; }
      try { bridge.chooseFolder(title, startDir, path => resolve(path || null)); }
      catch { resolve(null); }
    });
  }
  function pickFile(title: string, filter: string, startDir = ''): Promise<string | null> {
    return guarded(resolve => {
      const bridge = getBridge();
      if (!bridge?.chooseFile) { resolve(null); return; }
      try { bridge.chooseFile(title, startDir, filter, path => resolve(path || null)); }
      catch { resolve(null); }
    });
  }
  return { available, pickFolder, pickFile };
}
