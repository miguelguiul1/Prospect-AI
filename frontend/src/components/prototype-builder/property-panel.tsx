"use client";

import { Trash2, ArrowUp, ArrowDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { EmptyState } from "@/components/shared/empty-state";
import { definitionFor, type PropertyField } from "@/lib/prototype/component-registry";
import type { BuilderAction, BuilderState } from "@/components/prototype-builder/builder-reducer";
import type { PrimitiveValue } from "@/lib/prototype/types";

function FieldInput({
  field,
  value,
  onChange,
  onCommit,
}: {
  field: PropertyField;
  value: PrimitiveValue;
  onChange: (value: PrimitiveValue) => void;
  onCommit: () => void;
}) {
  const id = `field-${field.scope}-${field.key}`;

  if (field.kind === "textarea") {
    return (
      <Textarea
        id={id}
        value={typeof value === "string" ? value : ""}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onCommit}
        rows={3}
      />
    );
  }
  if (field.kind === "select") {
    return (
      <select
        id={id}
        value={typeof value === "string" ? value : (field.options?.[0]?.value ?? "")}
        onChange={(e) => {
          onChange(e.target.value);
          onCommit();
        }}
        className="h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm text-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none dark:bg-input/30"
      >
        {field.options?.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    );
  }
  if (field.kind === "number") {
    return (
      <Input
        id={id}
        type="number"
        value={typeof value === "number" ? value : ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
        onBlur={onCommit}
      />
    );
  }
  if (field.kind === "color") {
    return (
      <Input
        id={id}
        type="color"
        value={typeof value === "string" && value ? value : "#000000"}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onCommit}
        className="h-8 w-16 p-1"
      />
    );
  }
  return (
    <Input
      id={id}
      type="text"
      value={typeof value === "string" ? value : ""}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onCommit}
    />
  );
}

export function PropertyPanel({ state, dispatch }: { state: BuilderState; dispatch: (action: BuilderAction) => void }) {
  const selected = state.components.find((c) => c.id === state.selectedId);

  if (!selected) {
    return (
      <EmptyState
        title="Nenhum componente selecionado."
        description="Clique em um componente no canvas para editar suas propriedades."
        className="py-10"
      />
    );
  }

  const def = definitionFor(selected.type);

  return (
    <div className="flex flex-col gap-5" data-testid="property-panel">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-foreground">{def?.label ?? selected.type}</h4>
        <div className="flex gap-1">
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Mover para cima"
            onClick={() => dispatch({ type: "MOVE_SELECTED", direction: "up" })}
          >
            <ArrowUp className="size-3.5" />
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Mover para baixo"
            onClick={() => dispatch({ type: "MOVE_SELECTED", direction: "down" })}
          >
            <ArrowDown className="size-3.5" />
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Remover componente"
            onClick={() => dispatch({ type: "REMOVE_SELECTED" })}
          >
            <Trash2 className="size-3.5 text-destructive" />
          </Button>
        </div>
      </div>

      {def && def.fields.length > 0 ? (
        <div className="flex flex-col gap-4">
          {def.fields.map((field) => (
            <div key={`${field.scope}-${field.key}`} className="space-y-1.5">
              <Label htmlFor={`field-${field.scope}-${field.key}`}>{field.label}</Label>
              <FieldInput
                field={field}
                value={selected[field.scope][field.key] ?? null}
                onChange={(value) =>
                  dispatch({ type: "UPDATE_PROP", id: selected.id, scope: field.scope, key: field.key, value })
                }
                onCommit={() => dispatch({ type: "COMMIT_HISTORY" })}
              />
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">Este componente não tem propriedades editáveis.</p>
      )}
    </div>
  );
}
