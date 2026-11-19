/**
 * How to present a saved run error next to the provider the person picked.
 * This file stays free of Node builtins so a client component can import it.
 * @param {string} message
 * @param {{ provider?: string, cursor?: boolean, anthropic?: boolean }} state
 * @returns {{ showMessage: boolean, canContinue: boolean, text: string }}
 */
export function providerStatus(message, state) {
  const staleKey = /E_API_KEY/.test(String(message || ""));
  const provider = state.provider === "cursor" || state.provider === "anthropic" ? state.provider : "auto";
  const cursor = Boolean(state.cursor);
  const anthropic = Boolean(state.anthropic);
  const wantsAnthropic = provider === "anthropic";
  const wantsCursor = provider === "cursor" || (provider === "auto" && cursor && !anthropic);

  if ((wantsAnthropic || (provider === "auto" && !cursor)) && !anthropic && (staleKey || wantsAnthropic)) {
    return {
      showMessage: false,
      canContinue: false,
      text: cursor
        ? "Anthropic needs an API key. Choose Cursor to continue with the connected account."
        : "Connect Cursor, or add an Anthropic API key, before continuing.",
    };
  }
  if (staleKey && wantsCursor && cursor) {
    return { showMessage: false, canContinue: true, text: "" };
  }
  return { showMessage: true, canContinue: true, text: "" };
}
