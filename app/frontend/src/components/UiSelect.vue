<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

export interface UiSelectOption {
  value: string | number | null;
  label: string;
  disabled?: boolean;
  group?: string;
}

const props = withDefaults(defineProps<{
  modelValue: string | number | null;
  options: UiSelectOption[];
  disabled?: boolean;
  placeholder?: string;
  buttonClass?: string;
  menuClass?: string;
}>(), {
  disabled: false,
  placeholder: '請選擇',
  buttonClass: '',
  menuClass: ''
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | number | null): void;
}>();

const isOpen = ref(false);
const rootRef = ref<HTMLElement | null>(null);

const selectedOption = computed(() => props.options.find(opt => opt.value === props.modelValue));
const displayText = computed(() => selectedOption.value?.label || props.placeholder);

const groupedOptions = computed(() => {
  const order: string[] = [];
  const groups = new Map<string, UiSelectOption[]>();

  for (const option of props.options) {
    const groupName = option.group || '';
    if (!groups.has(groupName)) {
      groups.set(groupName, []);
      order.push(groupName);
    }
    groups.get(groupName)!.push(option);
  }

  return order.map(group => ({
    group,
    options: groups.get(group) || []
  }));
});

function toggleOpen() {
  if (props.disabled) return;
  isOpen.value = !isOpen.value;
}

function close() {
  isOpen.value = false;
}

function selectOption(option: UiSelectOption) {
  if (option.disabled) return;
  emit('update:modelValue', option.value);
  close();
}

function handleDocumentClick(event: MouseEvent) {
  if (!rootRef.value) return;
  if (!rootRef.value.contains(event.target as Node)) {
    close();
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    close();
  }
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick);
  document.addEventListener('keydown', handleKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick);
  document.removeEventListener('keydown', handleKeydown);
});
</script>

<template>
  <div ref="rootRef" class="relative">
    <button
      type="button"
      :disabled="disabled"
      :class="[
        'w-full flex items-center justify-between px-3 py-2 rounded-lg border border-white/20 bg-white/5 text-white focus:outline-none focus:border-blue-400 transition',
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:bg-white/10',
        buttonClass
      ]"
      @click="toggleOpen"
    >
      <span class="truncate text-left">{{ displayText }}</span>
      <span class="ml-2 text-white/70">▾</span>
    </button>

    <div
      v-if="isOpen"
      :class="[
        'absolute z-[120] mt-1 w-full max-h-72 overflow-y-auto rounded-lg border border-white/20 bg-slate-800 shadow-2xl',
        menuClass
      ]"
    >
      <template v-for="(group, idx) in groupedOptions" :key="`group-${idx}-${group.group || 'default'}`">
        <div v-if="group.group" class="px-3 py-2 text-xs text-white/50 bg-slate-900/70 border-b border-white/10">
          {{ group.group }}
        </div>
        <button
          v-for="option in group.options"
          :key="`${group.group || 'default'}-${String(option.value)}`"
          type="button"
          :disabled="option.disabled"
          class="w-full text-left px-3 py-2 text-sm transition"
          :class="[
            option.value === modelValue ? 'bg-blue-600/60 text-white' : 'text-slate-100',
            option.disabled ? 'opacity-40 cursor-not-allowed' : 'hover:bg-white/10'
          ]"
          @click="selectOption(option)"
        >
          {{ option.label }}
        </button>
      </template>
    </div>
  </div>
</template>
