import React, { useEffect, useRef, useState } from "react";
import {
  ArrowRightIcon,
  BookOpenIcon,
  DatabaseIcon,
  FileTextIcon,
  LogoMark,
  NetworkIcon,
  ShieldCheckIcon,
  SparklesIcon,
  StarIcon,
  ZapIcon,
} from "./Icons";

interface LandingPageProps {
  onLogin: () => void;
}

/* ── Intersection Observer hook for scroll-reveal ────────────────────── */
function useInView(options?: IntersectionObserverInit) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          obs.unobserve(el); // fire once
        }
      },
      { threshold: 0.15, rootMargin: "-60px", ...options }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return { ref, visible };
}

/* ── Animated counter ────────────────────────────────────────────────── */
function AnimatedStat({ value, suffix = "" }: { value: number; suffix?: string }) {
  const [count, setCount] = useState(0);
  const { ref, visible } = useInView();

  useEffect(() => {
    if (!visible) return;
    let frame: number;
    const duration = 1400;
    const start = performance.now();
    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out curve
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.round(eased * value));
      if (progress < 1) frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [visible, value]);

  return (
    <span ref={ref} className="landing-stat-number">
      {count.toLocaleString()}
      {suffix}
    </span>
  );
}

export function LandingPage({ onLogin }: LandingPageProps) {
  const [scrolled, setScrolled] = useState(false);

  /* Frosted nav appearance on scroll */
  useEffect(() => {
    function onScroll() {
      setScrolled(window.scrollY > 24);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  /* Scroll-reveal sections */
  const features = useInView();
  const stats = useInView();
  const trust = useInView();
  const cta = useInView();

  return (
    <div className="landing-page">
      {/* ── Ambient Glow Background ──────────────────────────────────── */}
      <div className="landing-ambient" aria-hidden="true">
        <div className="landing-orb landing-orb-1" />
        <div className="landing-orb landing-orb-2" />
        <div className="landing-orb landing-orb-3" />
      </div>

      {/* ── Glass Navigation ─────────────────────────────────────────── */}
      <nav className={`landing-nav ${scrolled ? "landing-nav--scrolled" : ""}`}>
        <div className="landing-nav-inner">
          <div className="landing-nav-brand">
            <LogoMark size={32} />
            <div className="landing-nav-brand-text">
              <span className="landing-nav-name">Field Desk</span>
              <span className="landing-nav-tagline">Knowledge Engine</span>
            </div>
          </div>

          <div className="landing-nav-links">
            <a href="#features" className="landing-nav-link">Features</a>
            <a href="#stats" className="landing-nav-link">Platform</a>
            <a href="#trust" className="landing-nav-link">Security</a>
          </div>

          <div className="landing-nav-actions">
            <button type="button" className="landing-btn-ghost" onClick={onLogin}>
              Sign in
            </button>
            <button type="button" className="landing-btn-primary" onClick={onLogin}>
              Get Started
              <ArrowRightIcon size={14} />
            </button>
          </div>
        </div>
      </nav>

      {/* ── Hero Section ─────────────────────────────────────────────── */}
      <section className="landing-hero">
        <div className="landing-hero-content">
          <div className="landing-hero-badge">
            <SparklesIcon size={14} />
            <span>Enterprise AI Knowledge Platform</span>
          </div>

          <h1 className="landing-hero-title">
            Your knowledge,
            <br />
            <span className="landing-hero-gradient">grounded in truth.</span>
          </h1>

          <p className="landing-hero-subtitle">
            Upload documents, connect data sources, and ask questions grounded in your
            organization's actual knowledge — powered by HNSW vector search and
            tenant-isolated AI.
          </p>

          <div className="landing-hero-cta-row">
            <button type="button" className="landing-btn-hero" onClick={onLogin}>
              Launch Knowledge Engine
              <ArrowRightIcon size={16} />
            </button>
            <button type="button" className="landing-btn-outline" onClick={() => {
              document.getElementById("features")?.scrollIntoView({ behavior: "smooth" });
            }}>
              Explore Features
            </button>
          </div>

          <div className="landing-hero-trust-row">
            <ShieldCheckIcon size={14} />
            <span>SOC-2 Compliant</span>
            <span className="landing-hero-dot">•</span>
            <span>AES-256 Encryption</span>
            <span className="landing-hero-dot">•</span>
            <span>Tenant Isolated</span>
          </div>
        </div>

        {/* Hero visual — floating glass card with mock UI */}
        <div className="landing-hero-visual">
          <div className="landing-hero-card">
            <div className="landing-hero-card-header">
              <div className="landing-hero-card-dots">
                <span /><span /><span />
              </div>
              <span className="landing-hero-card-label">Field Desk — Ask Intelligence</span>
            </div>
            <div className="landing-hero-card-body">
              <div className="landing-hero-chat-msg landing-hero-chat-user">
                <div className="landing-hero-chat-bubble-user">
                  What are our Q3 retention benchmarks vs. competitors?
                </div>
              </div>
              <div className="landing-hero-chat-msg landing-hero-chat-ai">
                <div className="landing-hero-chat-avatar">
                  <SparklesIcon size={16} />
                </div>
                <div className="landing-hero-chat-bubble-ai">
                  <div className="landing-hero-chat-thinking">
                    <span className="landing-typing-dot" />
                    <span className="landing-typing-dot" />
                    <span className="landing-typing-dot" />
                  </div>
                  Based on <strong>3 sources</strong> from your knowledge base, Q3
                  retention rate was <strong>94.2%</strong>, exceeding industry
                  average of 87.1%…
                </div>
              </div>
              <div className="landing-hero-sources">
                <span className="landing-hero-source-pill">
                  <FileTextIcon size={11} /> Q3_Metrics.pdf
                </span>
                <span className="landing-hero-source-pill">
                  <FileTextIcon size={11} /> Benchmark_2024.xlsx
                </span>
                <span className="landing-hero-source-pill">
                  <FileTextIcon size={11} /> Retention_Analysis.docx
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Features Grid ────────────────────────────────────────────── */}
      <section id="features" className="landing-section" ref={features.ref}>
        <div className={`landing-section-inner ${features.visible ? "landing-reveal" : ""}`}>
          <div className="landing-section-header">
            <span className="landing-section-badge">Core Capabilities</span>
            <h2 className="landing-section-title">Everything you need to harness your knowledge</h2>
            <p className="landing-section-desc">
              A complete platform for ingesting, indexing, and querying your organization's
              collective intelligence.
            </p>
          </div>

          <div className="landing-features-grid">
            {[
              {
                icon: StarIcon,
                title: "AI-Grounded Chat",
                desc: "Ask questions and get answers grounded in your actual documents — with source citations and confidence scores.",
                accent: "var(--primary)",
              },
              {
                icon: FileTextIcon,
                title: "Multi-Format Sources",
                desc: "Upload PDFs, DOCX, XLSX, PPTX, images, and more. Automatic text extraction, OCR, and semantic chunking.",
                accent: "var(--accent-cyan)",
              },
              {
                icon: NetworkIcon,
                title: "Knowledge Graph",
                desc: "Visualize relationships between concepts, documents, and entities with an interactive force-directed graph explorer.",
                accent: "var(--forest)",
              },
              {
                icon: BookOpenIcon,
                title: "Obsidian-Style Notes",
                desc: "Create and link notes with wikilinks, markdown, and bidirectional graph connections for deep knowledge work.",
                accent: "var(--amber)",
              },
              {
                icon: ZapIcon,
                title: "Data Connectors",
                desc: "Connect to Google Drive, Notion, Confluence, Slack, and more — keep your knowledge base automatically synced.",
                accent: "var(--signal)",
              },
              {
                icon: DatabaseIcon,
                title: "HNSW Vector Index",
                desc: "High-performance approximate nearest-neighbor search with pgvector HNSW indexing for sub-20ms query latency.",
                accent: "var(--accent-cyan)",
              },
            ].map((feat, i) => {
              const Icon = feat.icon;
              return (
                <div
                  key={feat.title}
                  className="landing-feature-card"
                  style={{ animationDelay: `${i * 60}ms` }}
                >
                  <div className="landing-feature-icon" style={{ color: feat.accent, background: `color-mix(in srgb, ${feat.accent} 12%, transparent)` }}>
                    <Icon size={22} />
                  </div>
                  <h3 className="landing-feature-title">{feat.title}</h3>
                  <p className="landing-feature-desc">{feat.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Stats Ribbon ─────────────────────────────────────────────── */}
      <section id="stats" className="landing-stats-section" ref={stats.ref}>
        <div className={`landing-section-inner ${stats.visible ? "landing-reveal" : ""}`}>
          <div className="landing-stats-grid">
            {[
              { value: 1536, suffix: "", label: "Embedding Dimensions", sub: "OpenAI text-embedding-3-large" },
              { value: 14, suffix: "ms", label: "Avg. Query Latency", sub: "HNSW approximate search" },
              { value: 50, suffix: "+", label: "File Formats", sub: "PDF, DOCX, XLSX, PPTX, images..." },
              { value: 99, suffix: ".9%", label: "Uptime SLA", sub: "Enterprise-grade reliability" },
            ].map((stat, i) => (
              <div
                key={stat.label}
                className="landing-stat-card"
                style={{ animationDelay: `${i * 80}ms` }}
              >
                <AnimatedStat value={stat.value} suffix={stat.suffix} />
                <span className="landing-stat-label">{stat.label}</span>
                <span className="landing-stat-sub">{stat.sub}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Trust & Security ─────────────────────────────────────────── */}
      <section id="trust" className="landing-section" ref={trust.ref}>
        <div className={`landing-section-inner ${trust.visible ? "landing-reveal" : ""}`}>
          <div className="landing-section-header">
            <span className="landing-section-badge">Enterprise Security</span>
            <h2 className="landing-section-title">Built for enterprise trust</h2>
            <p className="landing-section-desc">
              Every layer of Field Desk is designed with security, compliance, and data
              sovereignty as first-class priorities.
            </p>
          </div>

          <div className="landing-trust-grid">
            {[
              { title: "Tenant Isolation", desc: "Complete data segregation. Your vectors, documents, and embeddings never mix with other tenants." },
              { title: "AES-256 Encryption", desc: "Data encrypted at rest and in transit. Vector embeddings are stored in encrypted PostgreSQL columns." },
              { title: "SOC-2 Compliance", desc: "Audited controls for security, availability, and confidentiality. Enterprise-ready from day one." },
              { title: "RBAC & JWT Auth", desc: "Role-based access control with cryptographic JWT tokens. Least-privilege enforcement on every endpoint." },
              { title: "Rate Limiting", desc: "Configurable rate limits on AI generation endpoints. Protection against abuse and cost overruns." },
              { title: "OWASP Top 10", desc: "Input validation, parameterized queries, no hardcoded secrets. Defense-in-depth security architecture." },
            ].map((item, i) => (
              <div
                key={item.title}
                className="landing-trust-card"
                style={{ animationDelay: `${i * 50}ms` }}
              >
                <ShieldCheckIcon size={18} />
                <h4 className="landing-trust-title">{item.title}</h4>
                <p className="landing-trust-desc">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Final CTA ────────────────────────────────────────────────── */}
      <section className="landing-cta-section" ref={cta.ref}>
        <div className={`landing-cta-inner ${cta.visible ? "landing-reveal" : ""}`}>
          <div className="landing-cta-orb" aria-hidden="true" />
          <h2 className="landing-cta-title">Ready to ground your knowledge?</h2>
          <p className="landing-cta-desc">
            Start building your enterprise knowledge base in minutes. No credit card required.
          </p>
          <div className="landing-cta-actions">
            <button type="button" className="landing-btn-hero" onClick={onLogin}>
              Get Started Free
              <ArrowRightIcon size={16} />
            </button>
          </div>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <footer className="landing-footer">
        <div className="landing-footer-inner">
          <div className="landing-footer-brand">
            <LogoMark size={24} />
            <span>Field Desk</span>
          </div>
          <span className="landing-footer-copy">
            © {new Date().getFullYear()} Field Desk AI · Enterprise Knowledge Engine
          </span>
        </div>
      </footer>
    </div>
  );
}
