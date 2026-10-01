// @vitest-environment happy-dom
import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AssistantMarkdown } from "./AssistantMarkdown";

afterEach(cleanup);

it("removes executable HTML and dangerous link schemes", () => {
  const { container } = render(<AssistantMarkdown text={'<script>alert(1)</script>\n\n<img src=x onerror="alert(1)">\n\n[bad](javascript:alert(1))\n\n[ok](https://example.com)'} citations={[]} onSelect={vi.fn()} />);
  expect(container.querySelector("script, [onerror]")).toBeNull();
  expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
  const link = container.querySelector('a[href="https://example.com"]');
  expect(link?.getAttribute("rel")).toContain("noreferrer");
});

it("renders citation references as buttons without navigating", () => {
  const { container } = render(<AssistantMarkdown text="Evidence [source_1]" citations={[]} onSelect={vi.fn()} />);
  expect(container.querySelector("button.cite-chip")?.textContent).toBe("1");
  expect(container.querySelector("a")).toBeNull();
});
