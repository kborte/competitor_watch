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
        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm outline-none hover:border-slate-400 focus:ring-2 focus:ring-indigo-300"
      >
        <RadixSelect.Value />
        <RadixSelect.Icon className="text-slate-400">▾</RadixSelect.Icon>
      </RadixSelect.Trigger>
      <RadixSelect.Portal>
        <RadixSelect.Content
          position="popper"
          sideOffset={4}
          className="z-50 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg"
        >
          <RadixSelect.Viewport className="p-1">
            {options.map((opt) => (
              <RadixSelect.Item
                key={opt.value}
                value={opt.value}
                className="cursor-pointer rounded-md px-3 py-1.5 text-sm text-slate-700 outline-none data-[highlighted]:bg-indigo-50 data-[state=checked]:font-semibold data-[state=checked]:text-indigo-600"
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
