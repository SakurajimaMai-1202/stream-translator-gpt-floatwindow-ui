<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue';

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
const menuRef = ref<HTMLElement | null>(null);
const menuStyle = reactive({
  top: '0px',
  left: '0px',
  width: '0px',
  maxHeight: '18rem'
});
let positionFrame: number | null = null;
let listenersAttached = false;

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
  const target = event.target as Node;
  if (!rootRef.value) return;
  if (!rootRef.value.contains(target) && !menuRef.value?.contains(target)) {
    close();
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    close();
  }
}

function updateMenuPosition() {
  if (!rootRef.value) return;
  const rect = rootRef.value.getBoundingClientRect();
  const gap = 4;
  const viewportPadding = 12;
  const spaceBelow = window.innerHeight - rect.bottom - viewportPadding;
  const spaceAbove = rect.top - viewportPadding;
  const openUp = spaceBelow < 180 && spaceAbove > spaceBelow;
  const maxHeight = Math.max(140, Math.min(288, openUp ? spaceAbove - gap : spaceBelow - gap));

  menuStyle.left = `${Math.max(viewportPadding, Math.min(rect.left, window.innerWidth - rect.width - viewportPadding))}px`;
  menuStyle.width = `${rect.width}px`;
  menuStyle.maxHeight = `${maxHeight}px`;
  menuStyle.top = openUp
    ? `${Math.max(viewportPadding, rect.top - maxHeight - gap)}px`
    : `${Math.min(window.innerHeight - viewportPadding, rect.bottom + gap)}px`;
}

function scheduleMenuPositionUpdate() {
  if (!isOpen.value || positionFrame !== null) return;
  positionFrame = window.requestAnimationFrame(() => {
    positionFrame = null;
    updateMenuPosition();
  });
}

function attachOpenListeners() {
  if (listenersAttached) return;
  listenersAttached = true;
  document.addEventListener('pointerdown', handleDocumentClick);
  document.addEventListener('keydown', handleKeydown);
  window.addEventListener('resize', scheduleMenuPositionUpdate);
  window.addEventListener('scroll', scheduleMenuPositionUpdate, true);
}

function detachOpenListeners() {
  if (!listenersAttached) return;
  listenersAttached = false;
  document.removeEventListener('pointerdown', handleDocumentClick);
  document.removeEventListener('keydown', handleKeydown);
  window.removeEventListener('resize', scheduleMenuPositionUpdate);
  window.removeEventListener('scroll', scheduleMenuPositionUpdate, true);
  if (positionFrame !== null) {
    window.cancelAnimationFrame(positionFrame);
    positionFrame = null;
  }
}

watch(isOpen, async (open) => {
  if (!open) {
    detachOpenListeners();
    return;
  }
  attachOpenListeners();
  await nextTick();
  updateMenuPosition();
}, { flush: 'post' });

watch(() => props.options, () => {
  if (isOpen.value) nextTick(scheduleMenuPositionUpdate);
}, { flush: 'post' });

onBeforeUnmount(detachOpenListeners);
</script>

<template>
  <div ref="rootRef" class="relative">
    <button
      type="button"
      :disabled="disabled"
      :class="[
        'w-full flex items-center justify-between px-3 py-2 rounded-lg border border-white/20 bg-white/5 text-white focus:outline-none focus:border-blue-400 transition-colors',
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:bg-white/10',
        buttonClass
      ]"
      @click="toggleOpen"
    >
      <span class="truncate text-left">{{ displayText }}</span>
      <span class="ml-2 text-white/70">▾</span>
    </button>

    <Teleport to="body">
      <div
        v-if="isOpen"
        ref="menuRef"
        :style="menuStyle"
        :class="[
          'fixed z-[9999] overflow-y-auto rounded-lg border border-white/20 bg-slate-800 shadow-2xl',
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
            class="w-full text-left px-3 py-2 text-sm transition-colors"
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
    </Teleport>
  </div>
</template>
