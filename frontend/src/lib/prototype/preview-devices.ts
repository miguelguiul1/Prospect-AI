/**
 * Larguras de referência do preview responsivo (Prompt 13) — puramente de
 * apresentação: restringe a LARGURA DO CONTAINER que envolve o `Canvas`
 * em modo preview, nunca muda o `Component Tree` nem o schema de
 * componentes (`ComponentNode`). Valores de referência comuns de
 * indústria (não um breakpoint do Tailwind deste projeto, que não define
 * nenhum específico para "simular um dispositivo").
 *
 * Gap de schema conhecido, documentado aqui e no relatório do Prompt 13
 * (deliberadamente NÃO resolvido nesta fase sem antes perguntar — mudaria
 * o contrato usado pela geração por IA e pela validação existente):
 * `ComponentNode` não tem nenhum campo para comportamento responsivo REAL
 * (ex.: esconder um componente em mobile, mudar de row para column por
 * breakpoint). Trocar de dispositivo aqui só estreita o container — a
 * MESMA árvore renderiza dentro dele, então um layout que dependia da
 * largura real da tela (ex.: `row` com muitos itens) reflui naturalmente
 * via flexbox, mas nada pode ser condicionalmente diferente por
 * dispositivo além disso.
 */
export const PREVIEW_DEVICES = ["desktop", "tablet", "mobile"] as const;

export type PreviewDevice = (typeof PREVIEW_DEVICES)[number];

export const PREVIEW_DEVICE_WIDTH: Record<PreviewDevice, number> = {
  desktop: 1280,
  tablet: 768,
  mobile: 375,
};

export const PREVIEW_DEVICE_LABEL: Record<PreviewDevice, string> = {
  desktop: "Desktop",
  tablet: "Tablet",
  mobile: "Mobile",
};
