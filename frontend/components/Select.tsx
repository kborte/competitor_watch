"use client";

import * as RadixSelect from "@radix-ui/react-select";

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  ariaLabel: string;
}

// Shared Select wrapper — used for both the category and sort dropdowns, so
// they read as the same *kind* of control, visually distinct from the
// Window tabs (prominent segmented control) and the company logo chips.
export function Select({ value, onValueChange, options, ariaLabel }: SelectProps) {
  return (
    <RadixSelect.Root value={value} onValueChange={onValueChange}>
      <RadixSelect.Trigger
        aria-label={ariaLabel}
        className="inline-flex items-center gap-2 rounded-lg border border-[#e0e0ec] bg-white px-3 py-1.5 text-xs font-medium text-[#4a4a63] outline-none hover:border-[#c7c0fa] focus:ring-2 focus:ring-violet-200"
      >
        <RadixSelect.Value />
        <RadixSelect.Icon className="text-slate-400">▾</RadixSelect.Icon>
      </RadixSelect.Trigger>
      <RadixSelect.Portal>
        <RadixSelect.Content
          position="popper"
          sideOffset={4}
          className="z-50 overflow-hidden rounded-xl border border-[#e9e9f2] bg-white shadow-xl"
        >
          <RadixSelect.Viewport className="p-1">
            {options.map((opt) => (
              <RadixSelect.Item
                key={opt.value}
                value={opt.value}
                className="cursor-pointer rounded-lg px-3 py-2 text-xs text-[#31314a] outline-none data-[highlighted]:bg-[#f6f5fe] data-[state=checked]:font-semibold data-[state=checked]:text-[#5b4fe8]"
              >
                <RadixSelect.ItemText>{opt.label}</RadixSelect.ItemText>
              </RadixSelect.Item>
            ))}
          </RadixSelect.Viewport>
        </RadixSelect.Content>
      </RadixSelect.Portal>
    </RadixSelect.Root>
  );
}
