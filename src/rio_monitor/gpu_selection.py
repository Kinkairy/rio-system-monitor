"""Follow actual GPU engine load; never rotate adapters on a timer."""
import math

class ActiveGPU:
    def __init__(self):self.current=None;self.candidate=None;self.confirmations=0
    def select(self,readings):
        if not readings:self.current=None;return None
        by_id={row.identifier:row for row in readings}
        valid=[row for row in readings if isinstance(row.usage,(int,float)) and math.isfinite(row.usage)]
        previous=by_id.get(self.current)
        if not valid:return previous or readings[0]
        best=max(valid,key=lambda row:row.usage)
        if previous is None:
            self.current=best.identifier;return best
        load=previous.usage
        if not isinstance(load,(int,float)) or not math.isfinite(load):load=0
        if best.identifier==self.current or best.usage<1 or best.usage<=load+3:
            self.candidate=None;self.confirmations=0;return previous
        # A clear idle -> busy change is immediate. Two readings avoid switching
        # between simultaneously active adapters on a small transient spike.
        if load<1:self.current=best.identifier;self.candidate=None;self.confirmations=0;return best
        if self.candidate!=best.identifier:self.candidate=best.identifier;self.confirmations=1
        else:self.confirmations+=1
        if self.confirmations>=2:self.current=best.identifier;self.candidate=None;self.confirmations=0;return best
        return previous
