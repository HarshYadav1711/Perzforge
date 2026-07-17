import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { JobForm, validateJobForm } from "@/components/JobForm";

describe("validateJobForm", () => {
  it("rejects empty name and empty command", () => {
    expect(
      validateJobForm({
        name: "  ",
        image: "python:3.12-alpine",
        commandParts: [],
        gpu: false,
        timeout_minutes: 60,
      }),
    ).toEqual({ ok: false, error: "Name is required" });

    expect(
      validateJobForm({
        name: "job",
        image: "python:3.12-alpine",
        commandParts: ["", "  "],
        gpu: false,
        timeout_minutes: 60,
      }),
    ).toEqual({ ok: false, error: "Command must have at least one argument" });
  });

  it("builds a valid submit payload", () => {
    const result = validateJobForm({
      name: "train",
      image: "python:3.12-alpine",
      commandParts: ["python", "-c", "print(1)"],
      gpu: true,
      timeout_minutes: 30,
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.payload).toEqual({
        name: "train",
        spec: {
          image: "python:3.12-alpine",
          command: ["python", "-c", "print(1)"],
          env: {},
          gpu: true,
          timeout_minutes: 30,
        },
      });
    }
  });
});

describe("JobForm", () => {
  it("blocks submit when name is empty", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<JobForm onSubmit={onSubmit} />);

    await user.clear(screen.getByTestId("job-name"));
    await user.click(screen.getByTestId("job-submit"));

    expect(screen.getByTestId("job-form-error")).toHaveTextContent("Name is required");
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
