/** Keep live cadence; back off cached, warming and failed reads independently. */
export class RefreshSchedule {
  private nextAt=0
  private quietReads=0
  constructor(private readonly liveMs:number,private readonly maxQuietMs=30000){}
  due(now=Date.now()){return now>=this.nextAt}
  reset(){this.nextAt=0;this.quietReads=0}
  defer(milliseconds:number,now=Date.now()){this.nextAt=now+milliseconds;this.quietReads=0}
  received(status:string,now=Date.now()){
    this.quietReads=status==='FRESH'?0:Math.min(6,this.quietReads+1)
    const delay=this.quietReads?Math.min(this.maxQuietMs,this.liveMs*2**(this.quietReads-1)):this.liveMs
    this.nextAt=now+delay
  }
  failed(now=Date.now()){this.received('ERROR',now)}
}
