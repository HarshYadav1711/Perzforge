import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { KeyRevealModal } from "@/components/KeyRevealModal";

describe("KeyRevealModal", () => {
  it("shows the plaintext key, warning, and copy control", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    const onClose = vi.fn();
    render(<KeyRevealModal plaintextKey="pzf_test_secret_once" onClose={onClose} />);

    expect(screen.getByTestId("key-reveal-value")).toHaveTextContent("pzf_test_secret_once");
    expect(screen.getByTestId("key-reveal-warning")).toHaveTextContent(/won't see this again/i);

    await user.click(screen.getByTestId("key-reveal-copy"));
    expect(writeText).toHaveBeenCalledWith("pzf_test_secret_once");

    await user.click(screen.getByTestId("key-reveal-close"));
    expect(onClose).toHaveBeenCalled();
  });
});
