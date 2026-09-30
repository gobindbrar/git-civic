export default function Gap() {
  return (
    <div className="relative w-screen h-screen overflow-hidden bg-bg text-text font-body">
      <div className="absolute left-[6vw] top-[8vh] h-[0.7vh] w-[8vw] bg-accent" aria-hidden="true" />
      <h1 className="absolute left-[6vw] top-[14vh] font-display text-[5.4vw] font-medium tracking-[-0.045em]">The participation gap</h1>
      <div className="absolute left-[6vw] right-[6vw] top-[37vh]">
        <div className="flex items-center gap-[4vw] border-t border-[#d4d1c4] py-[4.5vh]">
          <span className="w-[9vw] font-display text-[4.2vw] text-accent">01</span>
          <p className="text-[2.7vw] font-semibold">Meeting notices spread across separate pages</p>
        </div>
        <div className="flex items-center gap-[4vw] border-t border-[#d4d1c4] py-[4.5vh]">
          <span className="w-[9vw] font-display text-[4.2vw] text-accent">02</span>
          <p className="text-[2.7vw] font-semibold">Agendas take time to scan</p>
        </div>
        <div className="flex items-center gap-[4vw] border-y border-[#d4d1c4] py-[4.5vh]">
          <span className="w-[9vw] font-display text-[4.2vw] text-accent">03</span>
          <p className="text-[2.7vw] font-semibold">Participation is easy to lose track of</p>
        </div>
      </div>
      <span className="absolute bottom-[4vh] right-[6vw] text-[1.5vw] text-muted">02 / 08</span>
    </div>
  );
}