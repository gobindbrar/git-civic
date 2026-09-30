export default function Next() {
  return (
    <div className="relative w-screen h-screen overflow-hidden bg-bg text-text font-body">
      <div className="absolute left-[6vw] top-[8vh] h-[0.7vh] w-[8vw] bg-accent" aria-hidden="true" />
      <h1 className="absolute left-[6vw] top-[14vh] font-display text-[5.4vw] font-medium tracking-[-0.045em]">What comes next</h1>
      <div className="absolute left-[6vw] right-[6vw] top-[38vh]">
        <p className="border-t border-[#d4d1c4] py-[4vh] text-[2.6vw] font-semibold leading-[1.25]">Broaden and monitor official meeting sources</p>
        <p className="border-t border-[#d4d1c4] py-[4vh] text-[2.6vw] font-semibold leading-[1.25]">Protect briefing capacity and reliability</p>
        <p className="border-y border-[#d4d1c4] py-[4vh] text-[2.6vw] font-semibold leading-[1.25]">Explore consent-based evidence verification</p>
      </div>
      <p className="absolute bottom-[7vh] left-[6vw] font-display text-[4.7vw] font-medium tracking-[-0.04em] text-primary">Find it. Show up. Prove it.</p>
    </div>
  );
}