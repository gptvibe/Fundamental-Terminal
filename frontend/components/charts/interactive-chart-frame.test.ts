// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";

function renderFrame() {
  const onExport = vi.fn();

  render(
    React.createElement(InteractiveChartFrame, {
      title: "Revenue trend",
      subtitle: "Inspect the reported trend at full scale.",
      badgeArea: React.createElement(
        "div",
        null,
        React.createElement("span", { className: "pill" }, "Source: SEC")
      ),
      controls: React.createElement(
        "button",
        { type: "button", className: "chart-chip" },
        "Quarterly"
      ),
      exportActions: [{ label: "Export CSV", onClick: onExport }],
      renderChart: ({ expanded }: { expanded: boolean }) =>
        React.createElement(
          "div",
          {
            "data-testid": expanded ? "expanded-chart" : "compact-chart",
            style: { width: "100%", height: expanded ? 420 : 220 },
          },
          expanded ? "Expanded chart" : "Compact chart"
        ),
    })
  );

  return { onExport };
}

function renderPolishedFrame() {
  const onReset = vi.fn();

  render(
    React.createElement(InteractiveChartFrame, {
      title: "Margin view",
      subtitle: "Expanded state wiring for the polished inspector.",
      annotations: [{ label: "Operating margin", color: "var(--accent)" }],
      footer: React.createElement("div", null, "Source: SEC filings"),
      resetState: { onReset },
      exportState: {
        pngFileName: "margin-view.png",
        csvFileName: "margin-view.csv",
        csvRows: [{ period: "2025", margin: 0.22 }],
      },
      renderChart: ({ expanded }: { expanded: boolean }) =>
        React.createElement(
          "div",
          {
            "data-testid": expanded ? "expanded-polished-chart" : "compact-polished-chart",
            style: { width: "100%", height: expanded ? 420 : 220 },
          },
          React.createElement(
            "svg",
            { width: 200, height: 100 },
            React.createElement("rect", { width: 200, height: 100, fill: "#111214" })
          )
        ),
    })
  );

  return { onReset };
}

describe("InteractiveChartFrame", () => {
  it("opens from card click and closes on escape", async () => {
    renderFrame();

    const card = screen.getByText("Revenue trend").closest("section");
    expect(card).toBeTruthy();

    fireEvent.click(card as HTMLElement);

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByTestId("expanded-chart")).toBeTruthy();

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });

  it("traps focus and restores focus to the trigger button", async () => {
    renderFrame();
    const user = userEvent.setup();

    const trigger = screen.getByRole("button", { name: /expand revenue trend/i });
    trigger.focus();

    await user.click(trigger);

    const closeButton = screen.getByRole("button", { name: "Close" });
    const controlsButton = screen.getByRole("button", { name: "Quarterly" });
    const exportButton = screen.getByRole("button", { name: "Export CSV" });

    await waitFor(() => {
      expect(document.activeElement).toBe(closeButton);
    });

    await user.tab();
    expect(document.activeElement).toBe(controlsButton);

    await user.tab();
    expect(document.activeElement).toBe(exportButton);

    await user.tab();
    expect(document.activeElement).toBe(closeButton);

    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(document.activeElement).toBe(trigger);
    });
  });

  it("suppresses invalid chart type options for time-series datasets", async () => {
    const user = userEvent.setup();

    render(
      React.createElement(InteractiveChartFrame, {
        title: "Trend mix",
        subtitle: "Time-series controls should only expose valid chart types.",
        controlState: {
          datasetKind: "time_series",
          chartType: "line",
          chartTypeOptions: ["line", "pie", "donut"],
          onChartTypeChange: vi.fn(),
        },
        renderChart: ({ expanded }: { expanded: boolean }) =>
          React.createElement(
            "div",
            {
              "data-testid": expanded ? "expanded-trend" : "compact-trend",
              style: { width: "100%", height: expanded ? 420 : 220 },
            },
            expanded ? "Expanded trend" : "Compact trend"
          ),
      })
    );

    await user.click(screen.getByRole("button", { name: /expand trend mix/i }));

    expect(screen.queryByRole("group", { name: "Chart type" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Pie" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Donut" })).toBeNull();
  });

  it("supports headerless inline cards while preserving the inspector title", async () => {
    const user = userEvent.setup();

    render(
      React.createElement(InteractiveChartFrame, {
        title: "Hidden header chart",
        subtitle: "Inline header stays hidden but the inspector still needs a title.",
        hideInlineHeader: true,
        renderChart: ({ expanded }: { expanded: boolean }) =>
          React.createElement(
            "div",
            {
              "data-testid": expanded ? "expanded-hidden-header" : "compact-hidden-header",
              style: { width: "100%", height: expanded ? 420 : 220 },
            },
            expanded ? "Expanded hidden header" : "Compact hidden header"
          ),
      })
    );

    expect(screen.queryByText("Hidden header chart")).toBeNull();

    await user.click(screen.getByRole("button", { name: /expand hidden header chart/i }));

    expect(screen.getByRole("heading", { name: "Hidden header chart" })).toBeTruthy();
  });

  it("only shows timeframe controls when the dataset supports them", async () => {
    const user = userEvent.setup();

    render(
      React.createElement(InteractiveChartFrame, {
        title: "Snapshot mix",
        subtitle: "Snapshot datasets should not expose time windows.",
        controlState: {
          datasetKind: "categorical_snapshot",
          timeframeMode: "snapshot",
          timeframeModeOptions: ["snapshot", "1y", "3y"],
          onTimeframeModeChange: vi.fn(),
        },
        renderChart: ({ expanded }: { expanded: boolean }) =>
          React.createElement(
            "div",
            {
              "data-testid": expanded ? "expanded-snapshot-mix" : "compact-snapshot-mix",
              style: { width: "100%", height: expanded ? 420 : 220 },
            },
            expanded ? "Expanded snapshot mix" : "Compact snapshot mix"
          ),
      })
    );

    await user.click(screen.getByRole("button", { name: /expand snapshot mix/i }));

    expect(screen.queryByRole("group", { name: "Window" })).toBeNull();
  });

  it("shows reset and shared export actions when export state is configured", async () => {
    const user = userEvent.setup();
    const { onReset } = renderPolishedFrame();

    await user.click(screen.getByRole("button", { name: /expand margin view/i }));

    expect(screen.getByRole("button", { name: "Reset view" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Export PNG" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Export CSV" })).toBeTruthy();
    expect(screen.getByText("Source: SEC filings")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Reset view" }));
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("renders the shared expanded empty state instead of the chart when requested", async () => {
    const user = userEvent.setup();

    render(
      React.createElement(InteractiveChartFrame, {
        title: "Sparse chart",
        subtitle: "No visible history in the current view.",
        stageState: {
          kind: "empty",
          kicker: "Sparse chart",
          title: "No visible history",
          message: "Widen the timeframe to inspect this chart.",
        },
        renderChart: ({ expanded }: { expanded: boolean }) =>
          React.createElement(
            "div",
            {
              "data-testid": expanded ? "expanded-sparse-chart" : "compact-sparse-chart",
              style: { width: "100%", height: expanded ? 420 : 220 },
            },
            expanded ? "Expanded sparse chart" : "Compact sparse chart"
          ),
      })
    );

    await user.click(screen.getByRole("button", { name: /expand sparse chart/i }));

    expect(screen.getByText("No visible history")).toBeTruthy();
    expect(screen.getByText("Widen the timeframe to inspect this chart.")).toBeTruthy();
    expect(screen.queryByTestId("expanded-sparse-chart")).toBeNull();
  });
});