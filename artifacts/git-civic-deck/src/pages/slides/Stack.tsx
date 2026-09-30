export default function Stack() {
  return (
    <div className="relative w-screen h-screen overflow-hidden bg-bg text-text font-body">
      <div className="absolute left-[6vw] top-[8vh] h-[0.7vh] w-[8vw] bg-accent" aria-hidden="true" />
      <h1 className="absolute left-[6vw] top-[14vh] font-display text-[5.4vw] font-medium tracking-[-0.045em]">Under the hood</h1>
      <div className="absolute left-[6vw] right-[6vw] top-[37vh]">
        <p className="border-t border-[#d4d1c4] py-[4.3vh] text-[2.4vw] leading-[1.2]">Flask + SQLite; HTML/CSS/JavaScript frontend</p>
        <p className="border-t border-[#d4d1c4] py-[4.3vh] text-[2.4vw] leading-[1.2]">SF official-site fallback; Seattle public Legistar API feed</p>
        <p className="border-t border-[#d4d1c4] py-[4.3vh] text-[2.4vw] leading-[1.2]">Optional source-cited AI briefing, provider-dependent</p>
        <p className="border-y border-[#d4d1c4] py-[4.3vh] text-[2.4vw] leading-[1.2]">SF Events API returns HTTP 400; Band path experimental and off</p>
      </div>
      <span className="absolute bottom-[4vh] right-[6vw] text-[1.5vw] text-muted">07 / 08</span>
    </div>
  );
}