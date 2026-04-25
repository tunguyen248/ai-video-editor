<template>
  <div class="page">
    <header class="site-header">
      <div class="brand">
        <span class="brand-mark">◆</span>
        <span class="brand-text">Reel Studio</span>
      </div>
      <nav class="nav">
        <a href="#features">Features</a>
        <a href="#workflow">Workflow</a>
        <a href="#proof">Proof</a>
      </nav>
      <button class="btn btn-outline">Book demo</button>
    </header>

    <main>
      <section class="hero">
        <p class="eyebrow">Built for modern post-production teams</p>
        <h1>Make every cut feel intentional.</h1>
        <p class="hero-copy">
          Reel Studio helps editors turn long footage into polished social clips with scene detection,
          smart highlight suggestions, and caption-ready exports in minutes.
        </p>
        <div class="hero-actions">
          <button class="btn btn-primary">Start your first reel</button>
          <button class="btn btn-ghost">Watch walkthrough</button>
        </div>
        <div class="metrics">
          <article v-for="item in metrics" :key="item.label">
            <p class="metric-value">{{ item.value }}</p>
            <p class="metric-label">{{ item.label }}</p>
          </article>
        </div>
      </section>

      <section id="features" class="section">
        <div class="section-head">
          <p class="eyebrow">Editorial-first feature set</p>
          <h2>A clean interface with strong production muscle.</h2>
        </div>
        <div class="feature-grid">
          <article class="card" v-for="feature in features" :key="feature.title">
            <p class="card-kicker">{{ feature.kicker }}</p>
            <h3>{{ feature.title }}</h3>
            <p>{{ feature.copy }}</p>
          </article>
        </div>
      </section>

      <section id="workflow" class="section warm-block">
        <div class="section-head narrow">
          <p class="eyebrow">How it works</p>
          <h2>Designed like an editor’s daily rhythm.</h2>
        </div>
        <ol class="steps">
          <li v-for="step in workflow" :key="step.title">
            <span>{{ step.index }}</span>
            <div>
              <h3>{{ step.title }}</h3>
              <p>{{ step.copy }}</p>
            </div>
          </li>
        </ol>
      </section>

      <section id="proof" class="section">
        <div class="section-head">
          <p class="eyebrow">Why teams switch</p>
          <h2>Fast enough for social. Refined enough for brand.</h2>
        </div>
        <div class="quote-grid">
          <article class="quote" v-for="quote in testimonials" :key="quote.person">
            <p>“{{ quote.text }}”</p>
            <footer>{{ quote.person }} · {{ quote.role }}</footer>
          </article>
        </div>
      </section>

      <section class="cta">
        <h2>Give your editors better tools than deadlines.</h2>
        <p>Ship scroll-stopping edits with a workflow that feels warm, focused, and deeply professional.</p>
        <button class="btn btn-primary">Request a private preview</button>
      </section>
    </main>

    <footer class="site-footer">
      <span>Reel Studio</span>
      <span>© {{ year }} — Crafted for video editors</span>
    </footer>
  </div>
</template>

<script setup>
const year = new Date().getFullYear()

const metrics = [
  { value: '3.2x', label: 'faster rough cuts' },
  { value: '94%', label: 'caption accuracy workflow' },
  { value: '8 min', label: 'average first reel output' }
]

const features = [
  {
    kicker: 'Scene intelligence',
    title: 'Automatic cut points that respect pacing',
    copy: 'Detect clean transitions and visual rhythm instantly so you can spend time shaping story, not scrubbing timelines.'
  },
  {
    kicker: 'Highlight scoring',
    title: 'Find moments worth posting',
    copy: 'Audio peaks, motion cues, and spoken emphasis are combined to surface sections with real editorial energy.'
  },
  {
    kicker: 'Caption pipeline',
    title: 'Accurate subtitles with brand-ready export',
    copy: 'Generate captions and downloadable transcripts quickly, then move straight into review with confidence.'
  }
]

const workflow = [
  {
    index: '01',
    title: 'Drop footage',
    copy: 'Upload interview, event, or creator content with no setup friction.'
  },
  {
    index: '02',
    title: 'Review suggested moments',
    copy: 'Scan intelligently scored clips and scene groups in a calm, structured layout.'
  },
  {
    index: '03',
    title: 'Export social-ready deliverables',
    copy: 'Render reels and captioned variants that are ready for publishing or client review.'
  }
]

const testimonials = [
  {
    text: 'Our team moved from chaotic manual clipping to a polished workflow in one week.',
    person: 'Nina P.',
    role: 'Senior Video Editor'
  },
  {
    text: 'It feels like software made by people who understand timing, typography, and pressure.',
    person: 'Marcus L.',
    role: 'Post-Production Lead'
  }
]
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,500;9..144,600&display=swap');

:global(*) { box-sizing: border-box; }
:global(body) {
  margin: 0;
  font-family: 'DM Sans', sans-serif;
  background: linear-gradient(180deg, #f8f2ea 0%, #f6f4ef 40%, #f3f1ec 100%);
  color: #1f1a17;
}

.page {
  max-width: 1120px;
  margin: 0 auto;
  padding: 2rem 1.5rem 3rem;
}

.site-header,
.site-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.site-header {
  padding: 0.6rem 0;
  position: sticky;
  top: 0;
  backdrop-filter: blur(8px);
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
}

.brand-mark { color: #b85c2d; }
.brand-text { letter-spacing: 0.02em; }

.nav { display: flex; gap: 1.25rem; }
.nav a {
  color: #4f423a;
  text-decoration: none;
  font-size: 0.95rem;
}

.hero {
  padding: 5.5rem 0 4rem;
  text-align: left;
  max-width: 820px;
}

.eyebrow {
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 0.72rem;
  color: #9b6a4b;
  margin-bottom: 1rem;
  font-weight: 600;
}

h1, h2, h3 {
  font-family: 'Fraunces', serif;
  margin: 0;
}

h1 {
  font-size: clamp(2.4rem, 6vw, 4.2rem);
  line-height: 1.03;
  max-width: 15ch;
}

.hero-copy {
  margin-top: 1.2rem;
  max-width: 60ch;
  color: #4d413a;
  font-size: 1.1rem;
}

.hero-actions { margin-top: 1.8rem; display: flex; gap: 0.85rem; flex-wrap: wrap; }

.btn {
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 0.75rem 1.2rem;
  font-weight: 600;
  background: transparent;
  cursor: pointer;
}

.btn-primary {
  background: #1f1a17;
  color: #f5ede4;
}

.btn-outline {
  border-color: #b7a79b;
  color: #3f342d;
}

.btn-ghost {
  border-color: #cfb6a4;
  color: #754f37;
}

.metrics {
  margin-top: 2.4rem;
  display: grid;
  grid-template-columns: repeat(3, minmax(130px, 1fr));
  gap: 0.9rem;
}

.metrics article {
  border: 1px solid #dccbbf;
  border-radius: 16px;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.46);
}

.metric-value { font-size: 1.35rem; font-weight: 700; margin: 0 0 0.2rem; }
.metric-label { margin: 0; color: #6b5950; font-size: 0.9rem; }

.section { margin-top: 3.8rem; }
.section-head { max-width: 760px; }
.section-head h2 {
  font-size: clamp(1.65rem, 4vw, 2.6rem);
  margin-top: 0.2rem;
}

.feature-grid,
.quote-grid {
  margin-top: 1.4rem;
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.card,
.quote {
  padding: 1.2rem;
  border-radius: 18px;
  border: 1px solid #dfd2c8;
  background: #fff9f4;
}

.card-kicker {
  margin: 0;
  color: #985d40;
  font-size: 0.78rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-weight: 700;
}

.card h3 { margin: 0.55rem 0; font-size: 1.3rem; }
.card p:last-child { margin: 0; color: #594c44; }

.warm-block {
  background: linear-gradient(135deg, #f1d6c4 0%, #f5ebdf 70%);
  border-radius: 24px;
  padding: 2rem;
}

.steps {
  margin: 1.4rem 0 0;
  list-style: none;
  padding: 0;
  display: grid;
  gap: 1rem;
}

.steps li {
  display: grid;
  grid-template-columns: 56px 1fr;
  gap: 1rem;
  align-items: start;
  border-top: 1px solid #cbaf9f;
  padding-top: 1rem;
}

.steps span {
  font-family: 'Fraunces', serif;
  font-size: 1.4rem;
  color: #8a4c2e;
}

.quote p {
  font-size: 1.05rem;
  margin: 0;
  color: #342b26;
}

.quote footer {
  margin-top: 0.95rem;
  color: #735f53;
  font-size: 0.9rem;
}

.cta {
  margin-top: 4rem;
  padding: 2rem;
  border-radius: 22px;
  background: #1f1a17;
  color: #efe6dc;
}

.cta h2 { font-size: clamp(1.5rem, 4vw, 2.2rem); }
.cta p { color: #dccfc1; max-width: 56ch; }

.site-footer {
  margin-top: 2.6rem;
  padding-top: 1rem;
  border-top: 1px solid #d8c9be;
  color: #76675d;
  font-size: 0.9rem;
}

@media (max-width: 760px) {
  .nav { display: none; }
  .metrics { grid-template-columns: 1fr; }
  .page { padding: 1.25rem 1rem 2.5rem; }
  .hero { padding-top: 3rem; }
}
</style>
