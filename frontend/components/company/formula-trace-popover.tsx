"use client";

import { useEffect, useRef } from "react";
import type { CompanyChartsFormulaTracePayload } from "@/lib/types";
import { formatCompactNumber } from "@/lib/format";

interface FormulaTracePopoverProps {
  trace: CompanyChartsFormulaTracePayload | null;
  isOpen: boolean;
  onClose: () => void;
}

export function FormulaTracePopover({ trace, isOpen, onClose }: FormulaTracePopoverProps) {
  const popoverRef = useRef<HTMLDivElement>(null);

  // Handle click-outside dismiss
  useEffect(() => {
    if (!isOpen) return;

    function handleClickOutside(event: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node)) {
        onClose();
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen, onClose]);

  // Handle Escape key dismiss
  useEffect(() => {
    if (!isOpen) return;

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  if (!isOpen || !trace) {
    return null;
  }

  return (
    <div
      ref={popoverRef}
      className="formula-trace-popover"
      role="dialog"
      aria-label="Formula trace details"
    >
      <div className="formula-trace-popover-inner">
        {/* Header: formula label and confidence */}
        <div className="formula-trace-header">
          <h3 className="formula-trace-title">{trace.formula_label}</h3>
          <span className={`formula-trace-confidence formula-trace-confidence-${trace.confidence}`}>{trace.confidence}</span>
        </div>

        {/* Formula template */}
        {trace.formula_template ? (
          <div className="formula-trace-section">
            <div className="formula-trace-label">Formula</div>
            <div className="formula-trace-template">{trace.formula_template}</div>
          </div>
        ) : null}

        {/* Computation breakdown */}
        {trace.formula_computation ? (
          <div className="formula-trace-section">
            <div className="formula-trace-label">Computation</div>
            <pre className="formula-trace-computation">{trace.formula_computation}</pre>
          </div>
        ) : null}

        {/* Inputs table */}
        {trace.inputs.length > 0 ? (
          <div className="formula-trace-section">
            <div className="formula-trace-label">Inputs</div>
            <div className="formula-trace-inputs">
              {trace.inputs.map((input) => (
                <div key={input.key} className="formula-trace-input-row">
                  <div className="formula-trace-input-label">{input.label}</div>
                  <div className="formula-trace-input-value">
                    <span className="formula-trace-input-number">{input.formatted_value}</span>
                    <span className="formula-trace-input-source">{input.source_kind}</span>
                    {input.source_detail ? <span className="formula-trace-input-detail">{input.source_detail}</span> : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {/* Result value */}
        {trace.result_value !== null ? (
          <div className="formula-trace-section formula-trace-result">
            <div className="formula-trace-label">Result</div>
            <div className="formula-trace-result-value">{formatCompactNumber(trace.result_value)}</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
