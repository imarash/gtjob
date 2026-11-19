"use client";

import { useState, type ComponentType, type FormEvent, type ReactNode } from "react";
import { RiUploadCloud2Line } from "@remixicon/react";
import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Select, SelectItem } from "@/components/base/select/select";
import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { Textarea } from "@/components/base/textarea/textarea";
import { ProviderSelect } from "@/components/studio/provider-select";
import { cx } from "@/utils/cx";

type IconComponent = ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;

export type SourceMode = "paste" | "library" | "upload";

export type SourceModeOption = {
  id: SourceMode;
  label: string;
};

export type ToolChoice = {
  id: string;
  title: string;
  summary: string;
  icon: IconComponent;
};

/**
 * Prose defaults to paste. A file defaults to the library when it has anything,
 * and to upload when it does not. Pass `mode` yourself to override this.
 */
export function defaultSourceMode(modes: SourceModeOption[], libraryCount: number): SourceMode {
  const ids = new Set(modes.map((mode) => mode.id));
  if (ids.has("paste")) return "paste";
  if (ids.has("library") && libraryCount > 0) return "library";
  if (ids.has("upload")) return "upload";
  return modes[0]?.id ?? "paste";
}

export function ToolPicker({
  tools,
  selectedId,
  onSelect,
}: {
  tools: ToolChoice[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div role="group" aria-label="Tools" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {tools.map((tool) => {
        const selected = tool.id === selectedId;
        const Icon = tool.icon;
        return (
          <button
            key={tool.id}
            type="button"
            aria-pressed={selected}
            onClick={() => onSelect(tool.id)}
            className={cx(
              "flex flex-col gap-3 rounded-3xl border p-4 text-start",
              "outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring",
              selected
                ? "border-accent-400 bg-background-secondary-default"
                : "border-border-button-default bg-background-primary-default hover:bg-background-secondary-hover",
            )}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="flex size-10 items-center justify-center rounded-full bg-background-tertiary-default">
                <Icon className="size-5 text-foreground-icon-secondary" aria-hidden />
              </span>
              {selected ? (
                <Chip variant="caption" color="blue">
                  Selected
                </Chip>
              ) : null}
            </span>
            <span className="flex flex-col gap-1">
              <span className="text-body-medium text-text-primary">{tool.title}</span>
              <span className="text-body-2-regular text-text-secondary">{tool.summary}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function Composer({
  title,
  provider,
  onProvider,
  providerDisabled = false,
  providerNote = "",
  submitLabel,
  pending = false,
  canSubmit,
  hint = "",
  onSubmit,
  extras,
  children,
}: {
  title: string;
  provider: string;
  onProvider: (next: string) => void;
  providerDisabled?: boolean;
  providerNote?: string;
  submitLabel: string;
  pending?: boolean;
  canSubmit: boolean;
  hint?: string;
  onSubmit: () => void;
  extras?: ReactNode;
  children: ReactNode;
}) {
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!pending && canSubmit) onSubmit();
  }

  return (
    <form className="flex flex-col gap-6 rounded-3xl border border-border-button-default p-6" onSubmit={submit}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <h2 className="text-headline-medium text-text-primary">{title}</h2>
        <ProviderSelect value={provider} onChange={onProvider} disabled={providerDisabled || pending} note={providerNote} />
      </div>
      {children}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">{extras}</div>
        <Button type="submit" disabled={pending || !canSubmit}>
          {pending ? "Working" : submitLabel}
        </Button>
      </div>
      {!canSubmit && hint ? <p className="text-body-2-regular text-text-secondary">{hint}</p> : null}
    </form>
  );
}

export function DocumentSource({
  legend,
  modes,
  mode,
  onMode,
  library = [],
  libraryName = "",
  onLibrary,
  libraryLabel,
  emptyLibrary,
  paste = "",
  onPaste,
  pasteLabel = "Paste text",
  pastePlaceholder = "",
  uploadLabel,
  uploadHint,
  accept,
  uploadedName,
  onFile,
  pending = false,
}: {
  legend: string;
  modes: SourceModeOption[];
  mode: SourceMode;
  onMode: (mode: SourceMode) => void;
  library?: string[];
  libraryName?: string;
  onLibrary: (name: string) => void;
  libraryLabel: string;
  emptyLibrary: string;
  paste?: string;
  onPaste?: (value: string) => void;
  pasteLabel?: string;
  pastePlaceholder?: string;
  uploadLabel: string;
  uploadHint: string;
  accept: string;
  uploadedName: string;
  onFile: (file: File) => void;
  pending?: boolean;
}) {
  const selectedLibrary = library.includes(libraryName) ? libraryName : (library[0] ?? "");

  return (
    <fieldset className="flex flex-col gap-3 border-0 p-0">
      <legend className="text-body-medium text-text-primary">{legend}</legend>
      {modes.length > 1 ? (
        <SegmentedControl
          className="self-start"
          aria-label={`${legend} source`}
          selectedKeys={new Set([mode])}
          onSelectionChange={(keys) => {
            const next = [...keys][0];
            if (next === "paste" || next === "library" || next === "upload") onMode(next);
          }}
        >
          {modes.map((item) => (
            <SegmentedControlItem key={item.id} id={item.id}>
              {item.label}
            </SegmentedControlItem>
          ))}
        </SegmentedControl>
      ) : null}
      {mode === "paste" ? (
        <Textarea
          aria-label={pasteLabel}
          placeholder={pastePlaceholder}
          value={paste}
          onChange={onPaste ?? (() => undefined)}
          rows={8}
          autoResize
          maxRows={16}
        />
      ) : null}
      {mode === "library" ? (
        library.length === 0 ? (
          <p className="text-body-regular text-text-secondary">{emptyLibrary}</p>
        ) : (
          <Select
            aria-label={libraryLabel}
            selectedKey={selectedLibrary}
            onSelectionChange={(key) => typeof key === "string" && onLibrary(key)}
          >
            {library.map((name) => (
              <SelectItem key={name} id={name}>
                {name}
              </SelectItem>
            ))}
          </Select>
        )
      ) : null}
      {mode === "upload" ? (
        <UploadWell
          label={uploadLabel}
          hint={uploadHint}
          accept={accept}
          fileName={uploadedName}
          disabled={pending}
          onFile={onFile}
        />
      ) : null}
    </fieldset>
  );
}

function UploadWell({
  label,
  hint,
  accept,
  fileName,
  disabled,
  onFile,
}: {
  label: string;
  hint: string;
  accept: string;
  fileName: string;
  disabled: boolean;
  onFile: (file: File) => void;
}) {
  const [dragOver, setDragOver] = useState(false);

  return (
    <label
      className={cx(
        "flex h-40 cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed bg-background-secondary-default px-4 text-center",
        dragOver ? "border-border-button-active" : "border-border-checkbox-default hover:border-border-button-active",
        disabled && "cursor-not-allowed opacity-60",
      )}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragOver(false);
        const file = event.dataTransfer.files?.[0];
        if (file && !disabled) onFile(file);
      }}
    >
      <input
        aria-label={label}
        type="file"
        accept={accept}
        disabled={disabled}
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onFile(file);
        }}
      />
      <span className="flex size-10 items-center justify-center rounded-full bg-file-upload-icon-background">
        <RiUploadCloud2Line className="size-6 text-file-upload-icon-foreground" aria-hidden />
      </span>
      <span className="text-body-medium text-text-primary">{fileName || hint}</span>
      <span className="text-body-2-regular text-text-secondary">PDF, Markdown, or text</span>
    </label>
  );
}
