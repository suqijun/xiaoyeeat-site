const { useEffect, useState } = React;

function IconDoc() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M4 2.5h5.2L12 5.3V13.5H4V2.5Z" stroke="currentColor" strokeWidth="1.4" />
      <path d="M9.1 2.6V5.4H12" stroke="currentColor" strokeWidth="1.4" />
      <path d="M5.8 8h4.4M5.8 10.4h3.2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function DoodleDoc(props) {
  return (
    <svg className={props.className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <rect x="10" y="8" width="26" height="32" rx="4" fill="#E8DEF8" />
      <path d="M12 8h16l8 8v24H12V8Z" stroke="currentColor" strokeWidth="2" />
      <path d="M28 8v8h8" stroke="currentColor" strokeWidth="2" />
      <path d="M18 22h12M18 28h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="36" cy="10" r="5" fill="#FDECC8" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function DoodlePhone(props) {
  return (
    <svg className={props.className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <rect x="15" y="6" width="18" height="36" rx="4" fill="#D6EAFD" />
      <rect x="16" y="6" width="16" height="36" rx="3" stroke="currentColor" strokeWidth="2" />
      <circle cx="24" cy="36" r="1.6" fill="currentColor" />
      <path d="M10 14c3-2 5 2 3 4M38 18c-3-1-4 3-2 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M34 8c4-3 8 1 6 5" stroke="#C45C3E" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function DoodleCheck(props) {
  return (
    <svg className={props.className} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <circle cx="24" cy="24" r="15" fill="#D3F5E2" />
      <circle cx="24" cy="24" r="14" stroke="currentColor" strokeWidth="2" />
      <path d="M16 24.5l5 5 11-12" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M38 10c3 2 2 7-2 7" stroke="#B0446A" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function App() {
  const w = window.WORKS;
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const scrollTo = (id) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="site" data-screen-label="works-home">
      <a className="skip" href="#main">跳到正文</a>

      <header className={"nav" + (scrolled ? " is-scrolled" : "")}>
        <a className="brand" href="/" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
          <span className="brand-mark">苏</span>
          {w.name} · Works
        </a>
        <nav className="nav-links" aria-label="站点">
          <button type="button" onClick={() => scrollTo("works")}>作品</button>
          <button type="button" onClick={() => scrollTo("about")}>关于</button>
        </nav>
        <div className="nav-actions">
          <button type="button" className="btn btn-primary" onClick={() => scrollTo("works")}>{w.ctaPrimary}</button>
        </div>
      </header>

      <main id="main" className="page">
        <section className="hero">
          <div className="hero-blobs" aria-hidden="true">
            <span className="blob blob-a" />
            <span className="blob blob-b" />
            <span className="blob blob-c" />
          </div>
          <h1>
            <span className="hl">可读、可试</span>的 AI 作品
          </h1>
          <p className="lede">{w.lede}</p>
          <div className="hero-ctas">
            <button type="button" className="btn btn-primary btn-lg" onClick={() => scrollTo("works")}>{w.ctaPrimary}</button>
            <a className="btn btn-secondary btn-lg" href="/lab">{w.ctaSecondary}</a>
          </div>
        </section>

        <div className="visual-wrap" id="works">
          <DoodleDoc className="doodle doodle-a" />
          <DoodlePhone className="doodle doodle-b" />
          <DoodleCheck className="doodle doodle-c" />
          <div className="sticky sticky-a" aria-hidden="true">可读</div>
          <div className="sticky sticky-b" aria-hidden="true">可试</div>

          <div className="window" aria-label="线索清洗：可读可试">
            <div className="window-chrome">
              <span className="dot"></span>
              <span className="dot"></span>
              <span className="dot"></span>
              <span className="window-title">{w.pair.title} · 可读可试</span>
            </div>
            <div className="window-body">
              <div className="pane">
                <p className="pane-label">可读</p>
                <a className="doc-row doc-row-solo" href="/articles/lead-cleaning">
                  <span className="doc-icon is-mint"><IconDoc /></span>
                  <span>
                    <strong>{w.pair.article.title}</strong>
                    <span>{w.pair.article.summary}</span>
                    <span className="doc-meta">{w.pair.article.time} · 打开文章</span>
                  </span>
                </a>
              </div>
              <div className="pane">
                <p className="pane-label">可试</p>
                <a className="lab-mini" href="/lab">
                  <span className="kind">{w.pair.lab.kind}</span>
                  <h3>{w.pair.lab.title}</h3>
                  <p>{w.pair.lab.summary}</p>
                  <div className="go">看怎么试 →</div>
                </a>
              </div>
            </div>
          </div>
        </div>

        <section className="more" id="more" aria-label="其他文章">
          <h2>其他文章</h2>
          <a className="more-row" href="/articles/logistics-sales">
            <span className="more-kind">{w.articles[0].kind}</span>
            <span className="more-body">
              <strong>{w.articles[0].title}</strong>
              <span>{w.articles[0].summary}</span>
            </span>
            <span className="more-meta">{w.articles[0].time} · 打开 →</span>
          </a>
        </section>

        <div className="proof" aria-label="经历">
          <span>曾供职 <strong>菜鸟 CRM</strong></span>
          <span>做过 <strong>字节房产</strong> 经营系统</span>
        </div>

        <section className="about" id="about">
          <h2><span className="hl">关于</span></h2>
          <p>{w.about}</p>
        </section>
      </main>

      <footer className="foot">
        <span>{w.domain}</span>
        <a href={w.icpHref} target="_blank" rel="noreferrer">{w.icp}</a>
      </footer>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
