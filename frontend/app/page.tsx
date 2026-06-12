import Link from 'next/link'

const features = [
  { icon: '🏦', title: 'Ngân hàng đề Bank-first', desc: 'Quản lý Bộ môn → Môn → Version → Bài → Câu hỏi → Release theo đúng luồng vận hành đề.' },
  { icon: '🧩', title: 'Tạo Quiz Open edX', desc: 'Tự map Course ID với Section, tạo Quiz theo FPT naming và gắn timer/cooldown bằng plugin.' },
  { icon: '📊', title: 'Theo dõi vận hành', desc: 'Biểu đồ câu hỏi, job, quiz, audit log và hoạt động giáo viên trong cùng hệ thống.' },
  { icon: '🔁', title: 'Publish & rollback', desc: 'Chốt release, publish lên Open edX Library, tạo Quiz và rollback nếu tạo nhầm.' },
]

const flow = ['Bộ môn', 'Môn', 'Version', 'Bài', 'Câu hỏi', 'Release', 'Quiz Open edX']

export default function Home() {
  return <div className="landing-page">
    <section className="landing-hero">
      <div className="landing-hero-copy">
        <div className="landing-kicker">Open edX AI Server · FPT Polytechnic</div>
        <h1>Máy chủ AI quản lý ngân hàng đề và tạo Quiz Open edX</h1>
        <p>
          Một nơi để giáo viên quản lý ngân hàng câu hỏi, duyệt release, tạo Quiz tự luyện có timer,
          theo dõi job và kiểm tra ai đã làm gì trong hệ thống.
        </p>
        <div className="landing-actions">
          <Link className="btn landing-primary" href="/bank">Vào Dashboard Bank</Link>
          <Link className="btn secondary" href="/bank/quiz">Tạo Quiz Open edX</Link>
        </div>
        <div className="landing-tags">
          <span>Next.js</span><span>FastAPI</span><span>PostgreSQL</span><span>Open edX Ulmo</span><span>Tutor 21</span>
        </div>
      </div>
      <div className="landing-product-card" aria-label="Tổng quan sản phẩm">
        <div className="product-card-top">
          <span className="product-logo">AI</span>
          <div><b>Quiz Bank Workbench</b><small>Bank-first workflow</small></div>
        </div>
        <div className="product-metrics">
          <div><b>4</b><span>Cấp quản lý</span></div>
          <div><b>100%</b><span>Review trước publish</span></div>
          <div><b>∞</b><span>Quiz bank</span></div>
        </div>
        <div className="product-flow">
          {flow.map((item, index) => <div key={item} className="product-flow-row">
            <span>{index + 1}</span><b>{item}</b>{index < flow.length - 1 ? <i>→</i> : <em>Ready</em>}
          </div>)}
        </div>
      </div>
    </section>

    <section className="landing-section">
      <div className="section-head landing-section-head">
        <div>
          <h2>Luồng mới gọn hơn cho giáo viên</h2>
          <p className="helper">Tập trung vào ngân hàng đề, version môn, bài học, câu hỏi và Quiz Open edX.</p>
        </div>
      </div>
      <div className="landing-feature-grid">
        {features.map((feature) => <article className="landing-feature-card" key={feature.title}>
          <span>{feature.icon}</span>
          <h3>{feature.title}</h3>
          <p>{feature.desc}</p>
        </article>)}
      </div>
    </section>

    <section className="landing-section landing-cta">
      <div>
        <h2>Sẵn sàng vận hành ngân hàng đề theo luồng Bank-first</h2>
        <p>Dashboard, lịch sử Quiz, job, audit và người dùng đã gom về luồng vận hành mới.</p>
      </div>
      <Link className="btn landing-primary" href="/bank">Mở hệ thống</Link>
    </section>
  </div>
}
