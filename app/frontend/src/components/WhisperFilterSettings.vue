<script setup lang="ts">
interface FilterOption {
  value: string;
  label: string;
  description: string;
}

const props = withDefaults(defineProps<{ modelValue?: string[] }>(), {
  modelValue: () => [],
});

const emit = defineEmits<{
  (event: 'update:modelValue', value: string[]): void;
}>();

const filterOptions: FilterOption[] = [
  { value: 'emoji_filter', label: 'Emoji 濾鏡', description: '移除辨識結果中的 emoji 符號。' },
  { value: 'repetition_filter', label: '重複內容濾鏡', description: '移除連續重複或異常循環的辨識內容。' },
  { value: 'japanese_stream_filter', label: '日文串流濾鏡', description: '改善日文串流辨識中常見的異常輸出。' },
];

function toggleFilter(filterName: string, checked: boolean) {
  const filters = new Set(props.modelValue);
  checked ? filters.add(filterName) : filters.delete(filterName);
  emit('update:modelValue', [...filters]);
}
</script>

<template>
  <div class="mt-6 pt-6 border-t border-white/10">
    <h3 class="text-lg font-semibold text-blue-300 mb-4">🔍 Whisper 結果濾鏡</h3>
    <p class="text-white/60 text-sm mb-4">選擇要套用在 Whisper 辨識結果上的後處理濾鏡。</p>
    <div class="space-y-3">
      <label
        v-for="option in filterOptions"
        :key="option.value"
        class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition-colors"
      >
        <input
          type="checkbox"
          :checked="modelValue.includes(option.value)"
          class="w-5 h-5 accent-blue-500 mt-0.5"
          @change="toggleFilter(option.value, ($event.target as HTMLInputElement).checked)"
        />
        <div class="flex-1">
          <span class="text-white font-medium">{{ option.label }}</span>
          <p class="text-white/50 text-sm mt-1">{{ option.description }}</p>
        </div>
      </label>
    </div>
  </div>
</template>
