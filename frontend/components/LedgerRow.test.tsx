// Component test for LedgerRow. Same unverified-in-this-sandbox
// caveat as lib/api.test.ts.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { LedgerRow } from "./LedgerRow";

describe("LedgerRow", () => {
  it("renders label and value", () => {
    render(<LedgerRow label="AAPL" value="$150.00" />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("$150.00")).toBeInTheDocument();
  });

  it("renders sublabel only when provided", () => {
    const { rerender } = render(<LedgerRow label="AAPL" value="$150" sublabel="10 shares" />);
    expect(screen.getByText("10 shares")).toBeInTheDocument();

    rerender(<LedgerRow label="AAPL" value="$150" />);
    expect(screen.queryByText("10 shares")).not.toBeInTheDocument();
  });

  it("applies gain class and a + sign for a positive changePct", () => {
    render(<LedgerRow label="AAPL" value="$150" changePct={0.05} />);
    const pct = screen.getByText("+5.0%");
    expect(pct).toHaveClass("gain");
  });

  it("applies loss class and no + sign for a negative changePct", () => {
    render(<LedgerRow label="AAPL" value="$150" changePct={-0.03} />);
    const pct = screen.getByText("-3.0%");
    expect(pct).toHaveClass("loss");
  });

  it("treats exactly zero as gain, not loss — matches the >= 0 convention in the component", () => {
    render(<LedgerRow label="AAPL" value="$150" changePct={0} />);
    const pct = screen.getByText("+0.0%");
    expect(pct).toHaveClass("gain");
  });

  it("renders no percentage row at all when changePct is null", () => {
    render(<LedgerRow label="AAPL" value="$150" changePct={null} />);
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("renders no percentage row at all when changePct is undefined", () => {
    render(<LedgerRow label="AAPL" value="$150" />);
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });
});
