"use client";

import { Monitor, Tablet, Smartphone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PREVIEW_DEVICES, PREVIEW_DEVICE_LABEL, type PreviewDevice } from "@/lib/prototype/preview-devices";

const ICON: Record<PreviewDevice, typeof Monitor> = {
  desktop: Monitor,
  tablet: Tablet,
  mobile: Smartphone,
};

/**
 * Seletor de largura de preview (Prompt 13) — só de apresentação, nunca
 * toca no `Component Tree` nem no reducer do Builder (`device` vive como
 * estado local em `PrototypeBuilder`, fora de `BuilderState`, então
 * trocar de dispositivo nunca marca `dirty`, nunca empilha undo/redo e
 * nunca afeta a seleção atual).
 */
export function PreviewDeviceSelector({
  device,
  onChange,
}: {
  device: PreviewDevice;
  onChange: (device: PreviewDevice) => void;
}) {
  return (
    <div role="group" aria-label="Largura do preview" className="flex items-center gap-0.5 rounded-lg border border-border p-0.5">
      {PREVIEW_DEVICES.map((d) => {
        const Icon = ICON[d];
        const active = d === device;
        return (
          <Button
            key={d}
            type="button"
            size="icon-sm"
            variant={active ? "secondary" : "ghost"}
            aria-pressed={active}
            aria-label={PREVIEW_DEVICE_LABEL[d]}
            onClick={() => onChange(d)}
          >
            <Icon className="size-3.5" />
          </Button>
        );
      })}
    </div>
  );
}
