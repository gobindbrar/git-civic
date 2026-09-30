const base = import.meta.env.BASE_URL;

export default function Title() {
  return (
    <div className="relative w-screen h-screen overflow-hidden bg-bg text-text font-body">
      <div className="absolute left-[6vw] top-[7vh] flex items-center gap-[1vw]">
        <div className="flex h-[2.6vw] items-end gap-[0.34vw]" aria-hidden="true">
          <span className="h-[1.5vw] w-[0.53vw] rounded-t-[0.25vw] bg-accent" />
          <span className="h-[2.6vw] w-[0.53vw] rounded-t-[0.25vw] bg-primary" />
          <span className="h-[2vw] w-[0.53vw] rounded-t-[0.25vw] bg-text" />
        </div>
        <span className="text-[1.7vw] font-extrabold tracking-[0.04em]">GIT <span className="font-semibold text-primary">CIVIC</span></span>
      </div>
      <div className="absolute left-[6vw] top-[32vh] z-10 w-[48vw]">
        <h1 className="font-display text-[8vw] font-medium leading-[0.94] tracking-[-0.055em]">GIT Civic</h1>
        <p className="mt-[5vh] text-[2.45vw] font-semibold leading-[1.27]">Find it. Show up. Prove it.</p>
        <p className="mt-[2vh] text-[1.7vw] leading-[1.4] text-muted">Nonpartisan civic participation demo</p>
      </div>
      <div className="absolute left-[52vw] top-[19vh] h-[65vh] w-[42vw] overflow-hidden border-[0.5vw] border-[#fbfaf5] shadow-[0_2vw_5vw_rgba(23,60,58,0.16)]">
        <img src={`${base}git-civic-home.jpg`} crossOrigin="anonymous" alt="Actual GIT Civic homepage" className="h-full w-full object-cover object-[46%_35%]" />
      </div>
      <div className="absolute bottom-[7vh] left-[6vw] h-[0.35vh] w-[37vw] bg-accent" aria-hidden="true" />
    </div>
  );
}