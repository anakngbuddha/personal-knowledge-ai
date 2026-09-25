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
import { SeaBubbles } from "./SeaBubbles";

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
      { threshold: 0.12, rootMargin: "-40px", ...options }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return { ref, visible };
}

/* ── Animated counter with luxury ease-out ───────────────────────────── */
function AnimatedStat({ value, suffix = "" }: { value: number; suffix?: string }) {
  const [count, setCount] = useState(0);
  const { ref, visible } = useInView();

  useEffect(() => {
    if (!visible) return;
    let frame: number;
    const duration = 1600;
    const start = performance.now();
    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Quintic ease-out for ultra-smooth luxury deceleration
      const eased = 1 - Math.pow(1 - progress, 5);
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

/* ── Interactive Simulation Presets ──────────────────────────────────── */
interface QueryPreset {
  id: string;
  tag: string;
  question: string;
  answer: string;
  metrics: string;
  sources: { name: string; type: string }[];
  confidence: number;
}

const QUERY_PRESETS: QueryPreset[] = [
  {
    id: "retention",
    tag: "Market Intel",
    question: "What are our Q3 enterprise retention benchmarks vs. competitors?",
    answer: "Based on 3 grounded sources from your enterprise knowledge base, Q3 net retention was 94.2%, outperforming the industry benchmark of 87.1% by 710 bps. Expansion revenue from tier-1 accounts drove 68% of the delta.",
    metrics: "12ms vector search · 99.4% grounded",
    confidence: 99.4,
    sources: [
      { name: "Q3_Enterprise_Metrics.pdf", type: "pdf" },
      { name: "SaaS_Benchmark_2024.xlsx", type: "xlsx" },
      { name: "Retention_Analysis.docx", type: "docx" },
    ],
  },
  {
    id: "architecture",
    tag: "Vector Scale",
    question: "How does the HNSW index partition multi-tenant embeddings?",
    answer: "The vector engine uses isolated HNSW graphs per tenant namespace in PostgreSQL. Each tenant query traverses dedicated index segments with m=16, ef_construction=64, guaranteeing zero cross-tenant vector leakage.",
    metrics: "8ms ANN traversal · 100% tenant-isolated",
    confidence: 100,
    sources: [
      { name: "HNSW_Architecture_Spec.md", type: "md" },
      { name: "Tenant_Isolation_Policy.pdf", type: "pdf" },
      { name: "Vector_Benchmark_Suite.py", type: "py" },
    ],
  },
  {
    id: "compliance",
    tag: "Security",
    question: "What cryptographic controls verify document provenance?",
    answer: "Every ingested block is fingerprinted with SHA-256 and anchored to cryptographic JWT claims. All vector embeddings are encrypted at rest with AES-256 and audited via SOC-2 compliant access logs.",
    metrics: "Zero trust · End-to-end verified",
    confidence: 99.8,
    sources: [
      { name: "SOC2_Type_II_Report.pdf", type: "pdf" },
      { name: "AES256_Key_Management.docx", type: "docx" },
      { name: "Audit_Trail_Schema.sql", type: "sql" },
    ],
  },
];

const ECOSYSTEM_PLATFORMS = [
  { name: "Google Drive", color: "#4285F4" },
  { name: "Notion", color: "#FFFFFF" },
  { name: "Confluence", color: "#0052CC" },
  { name: "Slack", color: "#E01E5A" },
  { name: "GitHub", color: "#6e40c9" },
  { name: "PostgreSQL", color: "#336791" },
  { name: "Snowflake", color: "#29B5E8" },
  { name: "Amazon S3", color: "#FF9900" },
  { name: "Linear", color: "#5E6AD2" },
  { name: "Obsidian", color: "#8A2BE2" },
  { name: "Zendesk", color: "#03363D" },
  { name: "ArXiv", color: "#B31B1B" },
];

export function LandingPage({ onLogin }: LandingPageProps) {
  const [scrolled, setScrolled] = useState(false);
  const [activePreset, setActivePreset] = useState<QueryPreset>(QUERY_PRESETS[0]);
  const [isTyping, setIsTyping] = useState(false);
  const [displayedAnswer, setDisplayedAnswer] = useState(activePreset.answer);

  /* 3D Tilt Card Ref */
  const heroCardRef = useRef<HTMLDivElement>(null);
  const heroContainerRef = useRef<HTMLDivElement>(null);

  /* Frosted nav appearance on scroll */
  useEffect(() => {
    function onScroll() {
      setScrolled(window.scrollY > 24);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  /* Simulated dynamic answer streaming on preset change */
  function selectPreset(preset: QueryPreset) {
    if (preset.id === activePreset.id) return;
    setActivePreset(preset);
    setIsTyping(true);
    setDisplayedAnswer("");

    let i = 0;
    const fullText = preset.answer;
    const timer = setInterval(() => {
      i += 3;
      if (i >= fullText.length) {
        setDisplayedAnswer(fullText);
        setIsTyping(false);
        clearInterval(timer);
      } else {
        setDisplayedAnswer(fullText.slice(0, i));
      }
    }, 18);
  }

  /* 3D Gyroscopic Perspective Tilt & Specular Spotlight for Hero Visual */
  useEffect(() => {
    const heroEl = heroContainerRef.current;
    const cardEl = heroCardRef.current;
    if (!heroEl || !cardEl) return;

    let rafId: number;
    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;

    function handleMouseMove(e: MouseEvent) {
      const rect = cardEl!.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      // Damped angle values
      const deltaX = (e.clientX - centerX) / (window.innerWidth / 2);
      const deltaY = (e.clientY - centerY) / (window.innerHeight / 2);

      targetX = Math.max(-10, Math.min(10, -deltaY * 10)); // rotateX
      targetY = Math.max(-12, Math.min(12, deltaX * 12));  // rotateY

      // Update spotlight position relative to the card
      const spotX = ((e.clientX - rect.left) / rect.width) * 100;
      const spotY = ((e.clientY - rect.top) / rect.height) * 100;
      cardEl!.style.setProperty("--spotlight-x", `${spotX}%`);
      cardEl!.style.setProperty("--spotlight-y", `${spotY}%`);
    }

    function handleMouseLeave() {
      targetX = 0;
      targetY = 0;
      cardEl!.style.setProperty("--spotlight-x", "50%");
      cardEl!.style.setProperty("--spotlight-y", "50%");
    }

    function renderTilt() {
      // Spring interpolation
      currentX += (targetX - currentX) * 0.1;
      currentY += (targetY - currentY) * 0.1;

      if (cardEl) {
        cardEl.style.transform = `perspective(1000px) rotateX(${currentX.toFixed(2)}deg) rotateY(${currentY.toFixed(2)}deg)`;
      }
      rafId = requestAnimationFrame(renderTilt);
    }

    heroEl.addEventListener("mousemove", handleMouseMove);
    heroEl.addEventListener("mouseleave", handleMouseLeave);
    rafId = requestAnimationFrame(renderTilt);

    return () => {
      heroEl.removeEventListener("mousemove", handleMouseMove);
      heroEl.removeEventListener("mouseleave", handleMouseLeave);
      cancelAnimationFrame(rafId);
    };
  }, []);

  /* Interactive Spotlight for Feature & Trust Cards */
  function handleCardMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    e.currentTarget.style.setProperty("--mouse-x", `${x}px`);
    e.currentTarget.style.setProperty("--mouse-y", `${y}px`);
  }

  /* Scroll-reveal sections */
  const features = useInView();
  const stats = useInView();
  const trust = useInView();
  const cta = useInView();

  return (
    <div className="landing-page">
      {/* ── Ambient Glow Background & Oceanic Bubbles Atmosphere ─────── */}
      <div className="landing-ambient" aria-hidden="true">
        <div className="landing-mesh-grid" />
        <div className="landing-orb landing-orb-1" />
        <div className="landing-orb landing-orb-2" />
        <div className="landing-orb landing-orb-3" />
        <div className="landing-shimmer-sweep" />
        <SeaBubbles count={26} variant="landing" interactive={true} />
      </div>

      {/* ── Glass Navigation ─────────────────────────────────────────── */}
      <nav className={`landing-nav ${scrolled ? "landing-nav--scrolled" : ""}`}>
        <div className="landing-nav-inner">
          <div className="landing-nav-brand">
            <div className="landing-nav-logo-wrap">
              <LogoMark size={34} />
              <div className="landing-nav-logo-glow" />
            </div>
            <div className="landing-nav-brand-text">
              <span className="landing-nav-name">Deep Atlas</span>
              <span className="landing-nav-tagline">Autonomous Knowledge Engine</span>
            </div>
          </div>

          <div className="landing-nav-links">
            <a href="#features" className="landing-nav-link">Features</a>
            <a href="#ecosystem" className="landing-nav-link">Ecosystem</a>
            <a href="#stats" className="landing-nav-link">Platform</a>
            <a href="#trust" className="landing-nav-link">Security</a>
          </div>

          <div className="landing-nav-actions">
            <button type="button" className="landing-btn-ghost" onClick={onLogin}>
              Sign in
            </button>
            <button type="button" className="landing-btn-primary" onClick={onLogin}>
              <span className="landing-btn-glow" />
              <span>Get Started</span>
              <ArrowRightIcon size={14} />
            </button>
          </div>
        </div>
      </nav>

      {/* ── Hero Section ─────────────────────────────────────────────── */}
      <section className="landing-hero" ref={heroContainerRef}>
        <div className="landing-hero-content">
          <div className="landing-hero-badge">
            <span className="landing-badge-pulse" />
            <SparklesIcon size={13} />
            <span>Deep Atlas — Autonomous Enterprise Intelligence</span>
          </div>

          <h1 className="landing-hero-title">
            <span className="landing-hero-line landing-hero-line-1">Your knowledge,</span>
            <span className="landing-hero-line landing-hero-line-2">
              <span className="landing-hero-gradient">grounded in truth.</span>
            </span>
          </h1>

          <p className="landing-hero-subtitle">
            Ingest corporate documents, connect live data repositories, and synthesize
            answers rigorously verified against your organization's verified source of truth —
            powered by Deep Atlas HNSW vector graphs and tenant-isolated AI.
          </p>

          <div className="landing-hero-cta-row">
            <button type="button" className="landing-btn-hero" onClick={onLogin}>
              <span className="landing-btn-hero-sheen" />
              <span>Launch Deep Atlas</span>
              <ArrowRightIcon size={16} />
            </button>
            <button
              type="button"
              className="landing-btn-outline"
              onClick={() => {
                document.getElementById("features")?.scrollIntoView({ behavior: "smooth" });
              }}
            >
              <span>Explore Architecture</span>
            </button>
          </div>

          <div className="landing-hero-trust-row">
            <div className="landing-trust-item">
              <ShieldCheckIcon size={14} />
              <span>SOC-2 Type II</span>
            </div>
            <span className="landing-hero-dot">•</span>
            <div className="landing-trust-item">
              <span className="landing-live-indicator" />
              <span>AES-256 Storage</span>
            </div>
            <span className="landing-hero-dot">•</span>
            <div className="landing-trust-item">
              <span>HNSW Sub-15ms Recall</span>
            </div>
          </div>
        </div>

        {/* Hero visual — 3D Tilt Glass Card with Live Query Simulation */}
        <div className="landing-hero-visual">
          {/* Satellite Floating Accents */}
          <div className="landing-hero-satellite landing-satellite-top">
            <span className="landing-satellite-dot" />
            <span>✦ HNSW Ingest: 1.2M vectors/sec</span>
          </div>
          <div className="landing-hero-satellite landing-satellite-bottom">
            <span className="landing-satellite-pulse" />
            <span>Verified Citation Precision: 99.8%</span>
          </div>

          <div className="landing-hero-card" ref={heroCardRef}>
            <div className="landing-hero-specular-light" />

            <div className="landing-atlas-hero-preview">
              <div className="landing-atlas-halo-glow" />
              <img
                src="/deep-atlas-hero.png"
                alt="Deep Atlas Bioluminescent Core"
                className="landing-atlas-hero-ray"
              />
              <div className="landing-atlas-hero-badge-pill">
                <span className="landing-live-indicator" />
                <span>DEEP ATLAS NEURAL CORE · ONLINE</span>
              </div>
            </div>

            <div className="landing-hero-card-header">
              <div className="landing-hero-card-dots">
                <span /><span /><span />
              </div>
              <span className="landing-hero-card-label">Deep Atlas Intelligence · Live Model Graph</span>
              <div className="landing-hero-header-badge">
                <span className="landing-live-indicator" />
                <span>ONLINE</span>
              </div>
            </div>

            {/* Interactive Query Presets Bar */}
            <div className="landing-preset-tabs">
              {QUERY_PRESETS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`landing-preset-tab ${activePreset.id === p.id ? "landing-preset-tab--active" : ""}`}
                  onClick={() => selectPreset(p)}
                >
                  <span className="landing-preset-tab-tag">{p.tag}</span>
                </button>
              ))}
            </div>

            <div className="landing-hero-card-body">
              {/* Question */}
              <div className="landing-hero-chat-msg landing-hero-chat-user">
                <div className="landing-hero-chat-bubble-user">
                  {activePreset.question}
                </div>
              </div>

              {/* Neural Synthesis Activity Indicator */}
              <div className="landing-neural-line">
                <div className="landing-neural-bar" />
                <div className="landing-neural-bar" />
                <div className="landing-neural-bar" />
                <div className="landing-neural-bar" />
                <div className="landing-neural-bar" />
                <span className="landing-neural-text">{activePreset.metrics}</span>
              </div>

              {/* AI Answer Bubble */}
              <div className="landing-hero-chat-msg landing-hero-chat-ai">
                <div className="landing-hero-chat-avatar">
                  <SparklesIcon size={15} />
                </div>
                <div className="landing-hero-chat-bubble-ai">
                  {isTyping && (
                    <div className="landing-hero-chat-thinking">
                      <span className="landing-typing-dot" />
                      <span className="landing-typing-dot" />
                      <span className="landing-typing-dot" />
                    </div>
                  )}
                  <span>{displayedAnswer}</span>
                  {isTyping && <span className="landing-type-cursor">|</span>}
                </div>
              </div>

              {/* Source Document Citations */}
              <div className="landing-hero-sources">
                <span className="landing-sources-label">CITED SOURCES:</span>
                {activePreset.sources.map((s) => (
                  <span key={s.name} className="landing-hero-source-pill">
                    <FileTextIcon size={11} /> {s.name}
                  </span>
                ))}
                <span className="landing-confidence-pill">
                  ★ {activePreset.confidence}% Confidence
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Luxury Infinite Ecosystem Stream (Marquee) ─────────────── */}
      <section id="ecosystem" className="landing-marquee-section">
        <div className="landing-marquee-label-wrap">
          <span className="landing-marquee-sub">SEAMLESS ENTERPRISE CONNECTIVITY</span>
        </div>
        <div className="landing-marquee-wrapper">
          <div className="landing-marquee-fade-left" />
          <div className="landing-marquee-fade-right" />
          <div className="landing-marquee-track">
            {[...ECOSYSTEM_PLATFORMS, ...ECOSYSTEM_PLATFORMS].map((p, i) => (
              <div key={`${p.name}-${i}`} className="landing-marquee-pill">
                <span className="landing-marquee-dot" style={{ backgroundColor: p.color }} />
                <span className="landing-marquee-name">{p.name}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Deep Atlas Bioluminescent Architecture Spotlight ─────── */}
      <section className="landing-atlas-spotlight-section">
        <div className="landing-atlas-spotlight-inner">
          <div className="landing-atlas-spotlight-badge">
            <span className="landing-live-indicator" />
            <span>Autonomous Knowledge Architecture</span>
          </div>
          <h2 className="landing-atlas-spotlight-title">
            Oceanic Depth. Neural Precision.
          </h2>
          <p className="landing-atlas-spotlight-desc">
            Like a manta ray navigating deep trenches with hydrodynamic grace, Deep Atlas traverses millions of high-dimensional document vectors with effortless 14ms recall and verifiable truth.
          </p>

          <div className="landing-atlas-spotlight-display">
            <div className="landing-atlas-ray-frame">
              <img
                src="/deep-atlas-hero.png"
                alt="Deep Atlas Manta Ray Knowledge Engine"
                className="landing-atlas-ray-art"
              />
              <div className="landing-atlas-ray-aura" />
            </div>

            <div className="landing-atlas-hotspots">
              <div className="landing-atlas-hotspot landing-hotspot-1">
                <div className="landing-hotspot-dot" />
                <div className="landing-hotspot-card">
                  <h4>Deep Trench Vector Ingestion</h4>
                  <p>1536-D HNSW indexing across multi-tenant PostgreSQL vector graphs with 14ms recall.</p>
                </div>
              </div>
              <div className="landing-atlas-hotspot landing-hotspot-2">
                <div className="landing-hotspot-dot" />
                <div className="landing-hotspot-card">
                  <h4>Bioluminescent Grounding</h4>
                  <p>Zero hallucinations. Cryptographic citation hashes anchored to exact source paragraphs.</p>
                </div>
              </div>
              <div className="landing-atlas-hotspot landing-hotspot-3">
                <div className="landing-hotspot-dot" />
                <div className="landing-hotspot-card">
                  <h4>Autonomous Exploration</h4>
                  <p>Graph theory clustering, semantic backlink networks, and living markdown wikis.</p>
                </div>
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
            <h2 className="landing-section-title">Engineered for depth, precision & velocity</h2>
            <p className="landing-section-desc">
              A sovereign enterprise architecture for ingesting, embedding, and interrogating
              your organization's multi-modal knowledge corpus.
            </p>
          </div>

          <div className="landing-features-grid">
            {[
              {
                icon: StarIcon,
                title: "AI-Grounded Chat",
                desc: "Synthesize exact answers anchored in real source documents — complete with verifiable paragraph anchors and confidence scores.",
                accent: "var(--primary)",
                pill: "Zero Hallucinations",
              },
              {
                icon: FileTextIcon,
                title: "Multi-Format Ingestion",
                desc: "Automatic parsing for PDFs, DOCX, XLSX, PPTX, images, and code with layout-preserving OCR and semantic block chunking.",
                accent: "var(--accent-cyan)",
                pill: "50+ Formats",
              },
              {
                icon: NetworkIcon,
                title: "Knowledge Graph Explorer",
                desc: "Discover latent associations between concepts, entities, and documents with GPU-accelerated force-directed graph exploration.",
                accent: "var(--forest)",
                pill: "Bi-directional",
              },
              {
                icon: BookOpenIcon,
                title: "Obsidian-Style Notes",
                desc: "Draft living markdown notes with bi-directional wikilinks, auto-backlinks, and seamless embedding into the global neural graph.",
                accent: "var(--amber)",
                pill: "Wikilinks",
              },
              {
                icon: ZapIcon,
                title: "Live Data Connectors",
                desc: "Synchronize continuously with Google Drive, Notion, Confluence, Slack, and GitHub with atomic delta updates and webhooks.",
                accent: "var(--signal)",
                pill: "Real-time Sync",
              },
              {
                icon: DatabaseIcon,
                title: "HNSW Vector Engine",
                desc: "Sub-15ms vector retrieval using pgvector HNSW indexing across 1,536-dimensional OpenAI and custom enterprise embeddings.",
                accent: "var(--accent-cyan)",
                pill: "Sub-15ms Latency",
              },
            ].map((feat) => {
              const Icon = feat.icon;
              return (
                <div
                  key={feat.title}
                  className="landing-feature-card"
                  onMouseMove={handleCardMouseMove}
                >
                  <div className="landing-card-spotlight" />
                  <div className="landing-feature-top-row">
                    <div
                      className="landing-feature-icon"
                      style={{
                        color: feat.accent,
                        background: `color-mix(in srgb, ${feat.accent} 14%, transparent)`,
                        borderColor: `color-mix(in srgb, ${feat.accent} 28%, transparent)`,
                      }}
                    >
                      <Icon size={22} />
                    </div>
                    <span className="landing-feature-pill">{feat.pill}</span>
                  </div>
                  <h3 className="landing-feature-title">{feat.title}</h3>
                  <p className="landing-feature-desc">{feat.desc}</p>
                  <div className="landing-card-bottom-accent" style={{ background: feat.accent }} />
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
              { value: 1536, suffix: "d", label: "Embedding Precision", sub: "OpenAI text-embedding-3-large" },
              { value: 14, suffix: "ms", label: "Average Query Latency", sub: "HNSW approximate graph traversal" },
              { value: 50, suffix: "+", label: "Supported Formats", sub: "PDF, DOCX, XLSX, PPTX, code, OCR" },
              { value: 99, suffix: ".9%", label: "Verified SLA Uptime", sub: "Enterprise HA multi-zone cluster" },
            ].map((stat) => (
              <div
                key={stat.label}
                className="landing-stat-card"
                onMouseMove={handleCardMouseMove}
              >
                <div className="landing-card-spotlight" />
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
            <span className="landing-section-badge">Enterprise Trust</span>
            <h2 className="landing-section-title">Cryptographic sovereignty at every tier</h2>
            <p className="landing-section-desc">
              Every query, block extraction, and embedding is guarded by cryptographic isolation
              and defense-in-depth security principles.
            </p>
          </div>

          <div className="landing-trust-grid">
            {[
              { title: "Tenant Isolation", desc: "Absolute vector segregation. Embeddings, raw documents, and cache buffers never co-mingle across customer boundaries." },
              { title: "AES-256 Storage", desc: "Military-grade encryption for all database columns, disk buffers, and network streams in transit and at rest." },
              { title: "SOC-2 Compliant", desc: "Rigorous audited security policies, role-based controls, and cryptographic audit log retention." },
              { title: "RBAC & JWT Security", desc: "Granular capability tokens with cryptographic signatures and least-privilege scoping across every endpoint." },
              { title: "Intelligent Rate Limiting", desc: "Adaptive token-bucket throttles on AI synthesis endpoints to prevent exhaustion and protect downstream budgets." },
              { title: "OWASP Hardened", desc: "Strict Pydantic boundary validation, parameterized ORM queries, and zero hardcoded credentials." },
            ].map((item) => (
              <div
                key={item.title}
                className="landing-trust-card"
                onMouseMove={handleCardMouseMove}
              >
                <div className="landing-card-spotlight" />
                <div className="landing-trust-icon-wrap">
                  <ShieldCheckIcon size={18} />
                  <span className="landing-trust-icon-ring" />
                </div>
                <h4 className="landing-trust-title">{item.title}</h4>
                <p className="landing-trust-desc">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Final Luxury CTA ─────────────────────────────────────────── */}
      <section className="landing-cta-section" ref={cta.ref}>
        <div className={`landing-cta-inner ${cta.visible ? "landing-reveal" : ""}`}>
          <div className="landing-cta-orb" aria-hidden="true" />
          <div className="landing-cta-glow-mesh" aria-hidden="true" />
          <span className="landing-section-badge">Deploy Deep Atlas</span>
          <h2 className="landing-cta-title">Ready to unlock your organization's collective intelligence?</h2>
          <p className="landing-cta-desc">
            Instantly ingest your documents, connect your existing tools, and interact with
            a knowledge engine that never invents, never leaks, and never stops learning.
          </p>
          <div className="landing-cta-actions">
            <button type="button" className="landing-btn-hero" onClick={onLogin}>
              <span className="landing-btn-hero-sheen" />
              <span>Get Started Now</span>
              <ArrowRightIcon size={16} />
            </button>
          </div>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <footer className="landing-footer">
        <div className="landing-footer-inner">
          <div className="landing-footer-brand">
            <LogoMark size={26} />
            <span>Deep Atlas</span>
            <span className="landing-footer-pill">v2.4 Enterprise</span>
          </div>
          <span className="landing-footer-copy">
            © {new Date().getFullYear()} Deep Atlas AI · High-Precision Enterprise Knowledge Platform
          </span>
        </div>
      </footer>
    </div>
  );
}

