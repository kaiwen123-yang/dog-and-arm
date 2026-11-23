"""Independent env/age draws on the existing ragged contact replay storage."""
import torch


class LaneAgeIndex:
    """Cache only (cohort, lane, time) integers; the stored TensorDicts remain in place."""
    def __init__(self, chunks, steps):
        entries = []
        for c, (_, starts) in enumerate(chunks):
            lt = starts[steps]
            if len(lt):
                entries.append(torch.column_stack((lt.new_full((len(lt),), c),lt)))
        self.table = None
        if entries:
            all_starts = torch.cat(entries)
            # Stable sorting preserves oldest-to-newest legal age within each env.
            self.table = all_starts[all_starts[:,1].argsort(stable=True)]
            self.counts = torch.bincount(self.table[:,1],minlength=chunks[0][0].batch_size[0])
            self.offsets = self.counts.cumsum(0) - self.counts

    def draw(self, batch):
        if self.table is None:
            return None
        # abc124c ReplayBuffer.sample chooses a feasible env uniformly first.
        # With complete measured histories, sample_causal's current frame is the
        # same env/age draw at L=1, conditioned here on a valid contact interval.
        lanes = torch.multinomial((self.counts>0).float(),batch,replacement=True)
        u = (torch.rand(batch,device=lanes.device)*self.counts[lanes].float()).long()
        return self.table[self.offsets[lanes]+u]


def gather_groups(chunks, starts, select):
    """Read just the sampled rows/windows from each participating cohort; retain draw order."""
    order = starts[:,0].argsort(stable=True)
    groups = starts[order]
    ids, counts = torch.unique_consecutive(groups[:,0],return_counts=True)
    pieces = []
    for cohort, group in zip(ids.tolist(), groups.split(counts.tolist()), strict=True):
        pieces.append(select(chunks[cohort][0],group[:,1],group[:,2]))
    return torch.cat(pieces)[order.argsort()]
