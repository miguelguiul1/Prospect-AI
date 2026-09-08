import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toolbar } from "@/components/prototype-builder/toolbar";
import type { BuilderState } from "@/components/prototype-builder/builder-reducer";

// Prompt 10, seção 3 (auditoria de cobertura): `Toolbar` só era exercitado
// indiretamente via `prototype-builder.test.tsx`, que nunca testava
// renomear o protótipo nem os botões de desfazer/refazer — as interações
// mais simples e mais usadas da barra de ferramentas.

function baseState(overrides: Partial<BuilderState> = {}): BuilderState {
  return {
    components: [],
    selectedId: null,
    mode: "edit",
    past: [],
    future: [],
    dirty: false,
    historyLocked: false,
    ...overrides,
  };
}

describe("Toolbar", () => {
  it("typing in the name field calls onNameChange with the new value", async () => {
    const onNameChange = vi.fn();
    render(
      <Toolbar
        prototypeId="proto-1"
        state={baseState()}
        dispatch={vi.fn()}
        name="Original"
        onNameChange={onNameChange}
        onSave={vi.fn()}
        saving={false}
        dirty={false}
      />
    );

    await userEvent.type(screen.getByLabelText("Nome do protótipo"), "X");

    expect(onNameChange).toHaveBeenCalled();
  });

  it("undo button is disabled with no history and dispatches UNDO when enabled", async () => {
    const dispatch = vi.fn();
    const { rerender } = render(
      <Toolbar prototypeId="proto-1" state={baseState()} dispatch={dispatch} name="X" onNameChange={vi.fn()} onSave={vi.fn()} saving={false} dirty={false} />
    );
    expect(screen.getByRole("button", { name: "Desfazer" })).toBeDisabled();

    rerender(
      <Toolbar
        prototypeId="proto-1"
        state={baseState({ past: [[]] })}
        dispatch={dispatch}
        name="X"
        onNameChange={vi.fn()}
        onSave={vi.fn()}
        saving={false}
        dirty={false}
      />
    );
    const undoButton = screen.getByRole("button", { name: "Desfazer" });
    expect(undoButton).toBeEnabled();

    await userEvent.click(undoButton);
    expect(dispatch).toHaveBeenCalledWith({ type: "UNDO" });
  });

  it("redo button is disabled with no future and dispatches REDO when enabled", async () => {
    const dispatch = vi.fn();
    render(
      <Toolbar
        prototypeId="proto-1"
        state={baseState({ future: [[]] })}
        dispatch={dispatch}
        name="X"
        onNameChange={vi.fn()}
        onSave={vi.fn()}
        saving={false}
        dirty={false}
      />
    );

    const redoButton = screen.getByRole("button", { name: "Refazer" });
    expect(redoButton).toBeEnabled();
    await userEvent.click(redoButton);
    expect(dispatch).toHaveBeenCalledWith({ type: "REDO" });
  });

  it("save button reflects the dirty/saving combination", () => {
    const { rerender } = render(
      <Toolbar prototypeId="proto-1" state={baseState()} dispatch={vi.fn()} name="X" onNameChange={vi.fn()} onSave={vi.fn()} saving={false} dirty={false} />
    );
    expect(screen.getByRole("button", { name: /^salvar$/i })).toBeDisabled();

    rerender(
      <Toolbar prototypeId="proto-1" state={baseState()} dispatch={vi.fn()} name="X" onNameChange={vi.fn()} onSave={vi.fn()} saving={false} dirty={true} />
    );
    expect(screen.getByRole("button", { name: /^salvar$/i })).toBeEnabled();
    expect(screen.getByText("Alterações não salvas")).toBeInTheDocument();

    rerender(
      <Toolbar prototypeId="proto-1" state={baseState()} dispatch={vi.fn()} name="X" onNameChange={vi.fn()} onSave={vi.fn()} saving={true} dirty={true} />
    );
    expect(screen.getByText("Salvando…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /salvando/i })).toBeDisabled();
  });

  it("clicking save calls onSave", async () => {
    const onSave = vi.fn();
    render(
      <Toolbar prototypeId="proto-1" state={baseState()} dispatch={vi.fn()} name="X" onNameChange={vi.fn()} onSave={onSave} saving={false} dirty={true} />
    );

    await userEvent.click(screen.getByRole("button", { name: /^salvar$/i }));
    expect(onSave).toHaveBeenCalledOnce();
  });

  it("toggling mode dispatches SET_MODE with the opposite mode", async () => {
    const dispatch = vi.fn();
    render(
      <Toolbar prototypeId="proto-1" state={baseState({ mode: "edit" })} dispatch={dispatch} name="X" onNameChange={vi.fn()} onSave={vi.fn()} saving={false} dirty={false} />
    );

    await userEvent.click(screen.getByRole("button", { name: /preview/i }));
    expect(dispatch).toHaveBeenCalledWith({ type: "SET_MODE", mode: "preview" });
  });
});
