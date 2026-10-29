"use client";

import { Radio, RadioGroup } from "react-aria-components";
import { Checkbox } from "@/components/base/checkbox/checkbox";
import { Textarea } from "@/components/base/textarea/textarea";
import { controlKind, questionChoices } from "@/lib/answer-select.mjs";
import { cx } from "@/utils/cx";

export type StudioQuestion = {
  id: string;
  prompt?: string;
  type?: string;
  choices?: { id: string; label: string }[];
  allow_free_text?: boolean;
  default?: { choice_ids?: string[]; description?: string; text?: string };
  status?: string;
};

function isBoundaryHandoff(label: string) {
  return /\btouch(?:es|ed|ing)?\b/i.test(label) || /boundary month/i.test(label) || /both overlap in \d{4}\b/i.test(label);
}

function RadioMark({ selected, hovered }: { selected: boolean; hovered: boolean }) {
  return (
    <span
      aria-hidden
      className={cx(
        "flex size-4 shrink-0 items-center justify-center rounded-full border transition-[background-color,border-color,box-shadow] duration-150",
        selected
          ? "border-transparent bg-linear-to-b from-accent-500 to-accent-600 shadow-checkbox-selected"
          : cx(
              "bg-background-primary-default shadow-xs",
              hovered ? "border-border-checkbox-hover" : "border-border-checkbox-default",
            ),
      )}
    >
      {selected ? <span className="size-1.5 rounded-full bg-background-primary-default" /> : null}
    </span>
  );
}

export function QuestionFields({
  questions,
  picked,
  notes,
  onToggle,
  onNote,
}: {
  questions: StudioQuestion[];
  picked: Record<string, string[]>;
  notes: Record<string, string>;
  onToggle: (questionId: string, choiceId: string, selected: boolean, kind: "multiple" | "single") => void;
  onNote: (questionId: string, text: string) => void;
}) {
  return (
    <div className="flex flex-col gap-6">
      {questions.map((question) => {
        const kind = controlKind(question);
        const choices = questionChoices(question).filter((choice) => !isBoundaryHandoff(choice.label));
        const selected = picked[question.id] || [];
        if ((kind === "multiple" || kind === "single") && choices.length === 0) return null;
        return (
          <fieldset key={question.id} className="flex flex-col gap-3">
            <legend className="text-body-regular text-text-primary">
              <span className="text-body-medium text-text-secondary">{question.id}. </span>
              {question.prompt}
            </legend>
            {kind === "multiple" ? (
              <div className="flex flex-col gap-1">
                {choices.map((choice) => (
                  <Checkbox
                    key={choice.id}
                    className="items-start rounded-lg px-2 py-1.5 hover:bg-background-secondary-default"
                    isSelected={selected.includes(choice.id)}
                    onChange={(on) => onToggle(question.id, choice.id, on, "multiple")}
                  >
                    {choice.label}
                  </Checkbox>
                ))}
              </div>
            ) : null}
            {kind === "single" ? (
              <RadioGroup
                aria-label={question.prompt || question.id}
                value={selected[0] || ""}
                onChange={(value) => onToggle(question.id, value, true, "single")}
                className="flex flex-col gap-1"
              >
                {choices.map((choice) => (
                  <Radio
                    key={choice.id}
                    value={choice.id}
                    className="group relative flex cursor-pointer items-start gap-2 rounded-lg px-2 py-1.5 text-body-medium text-text-primary outline-none hover:bg-background-secondary-default"
                  >
                    {({ isSelected, isHovered, isFocusVisible }) => (
                      <>
                        <span className={cx(isFocusVisible && "rounded-full ring-2 ring-border-focus-ring")}>
                          <RadioMark selected={isSelected} hovered={isHovered} />
                        </span>
                        <span>{choice.label}</span>
                      </>
                    )}
                  </Radio>
                ))}
              </RadioGroup>
            ) : null}
            {kind === "text" ? (
              <Textarea
                aria-label={question.prompt || question.id}
                placeholder={question.default?.text || "Write the figure, or leave this blank"}
                rows={2}
                autoResize
                maxRows={6}
                value={notes[question.id] || ""}
                onChange={(value) => onNote(question.id, value)}
              />
            ) : null}
            {question.default?.description ? (
              <p className="text-body-2-regular text-text-secondary">{question.default.description}</p>
            ) : null}
          </fieldset>
        );
      })}
    </div>
  );
}
