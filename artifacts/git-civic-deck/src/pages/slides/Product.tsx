const base = import.meta.env.BASE_URL;

export default function Product() {
  return (
    <div className="relative w-screen h-screen overflow-hidden bg-bg text-text font-body">
      <div className="absolute left-[6vw] top-[8vh] h-[0.7vh] w-[8vw] bg-accent" aria-hidden="true" />
      <h1 className="absolute left-[6vw] top-[14vh] w-[50vw] font-display text-[5.3vw] font-medium leading-[1.03] tracking-[-0.045em]">One place to take part</h1>
      <div className="absolute left-[6vw] top-[45vh] w-[41vw] space-y-[5vh]">
        <p className="border-t border-[#d4d1c4] pt-[2.5vh] text-[2.35vw] font-semibold leading-[1.35]">Find public meetings near you</p>
        <p className="border-t border-[#d4d1c4] pt-[2.5vh] text-[2.35vw] font-semibold leading-[1.35]">See agenda details and official links</p>
        <p className="border-t border-[#d4d1c4] pt-[2.5vh] text-[2.35vw] font-semibold leading-[1.35]">Keep a private record of participation</p>
      </div>
      <div className="absolute left-[52vw] top-[22vh] h-[63vh] w-[43vw] overflow-hidden border-[0.45vw] border-[#fbfaf5] shadow-[0_1.5vw_4vw_rgba(23,60,58,0.13)]">
        <img src={`${base}git-civic-home.jpg`} crossOrigin="anonymous" alt="GIT Civic discovery interface showing meeting search and calendar" className="h-full w-full object-cover object-[56%_70%]" />
      </div>
      <span className="absolute bottom-[4vh] left-[6vw] text-[1.5vw] text-muted">03 / 08</span>
    </div>
  );
}