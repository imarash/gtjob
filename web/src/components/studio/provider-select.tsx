"use client";

import { Select, SelectItem } from "@/components/base/select/select";

export function ProviderSelect({
  value,
  onChange,
  disabled = false,
  note = "",
}: {
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  note?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span className="text-body-2-regular text-text-secondary">Model</span>
        <div className="w-36">
          <Select
            aria-label="Model"
            size="sm"
            selectedKey={value || "cursor"}
            isDisabled={disabled}
            onSelectionChange={(key) => {
              if (key === "auto" || key === "cursor" || key === "anthropic") onChange(key);
            }}
          >
            <SelectItem id="cursor">Cursor</SelectItem>
            <SelectItem id="anthropic">Anthropic</SelectItem>
            <SelectItem id="auto">Automatic</SelectItem>
          </Select>
        </div>
      </div>
      {note ? <p className="max-w-sm text-body-2-regular text-text-secondary">{note}</p> : null}
    </div>
  );
}
