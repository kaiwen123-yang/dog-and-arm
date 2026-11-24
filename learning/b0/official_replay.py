"""Physical-tick ring for the fixed runner's lane then age sampling law."""
import torch
from tensordict import TensorDict


class OfficialReplay:
    def __init__(self, lanes, capacity, device):
        self.lanes, self.capacity, self.device = lanes, capacity, device
        self.clock = 0
        self.page_size = 25
        self.pages = {}
        self.streak = torch.zeros(lanes, device=device, dtype=torch.int32)
        self.episode = torch.zeros_like(self.streak, dtype=torch.long)
        self.valid_length = torch.zeros(lanes, capacity, device=device, dtype=torch.int32)
        self.index = {}
        self.receipt = None

    def append(self, rows):
        row, = rows
        slot = self.clock % self.capacity
        page, offset = divmod(slot, self.page_size)
        if page not in self.pages:
            size = min(self.page_size, self.capacity - page * self.page_size)
            self.pages[page] = {k: t.new_zeros((size, *t.shape)) for k, t in row.items()}
        for k, t in row.items():
            self.pages[page][k][offset].copy_(t)
        self.streak = torch.where(row['valid'], 1 + self.streak * (self.episode == row['episode']), 0)
        self.episode = row['episode']
        self.valid_length[:, slot] = self.streak
        self.clock += 1
        self.index.clear()

    def positions(self, h):
        if h not in self.index:
            size = min(self.clock, self.capacity)
            # Rows are indexed by the final measured transition, oldest first.
            slots = (torch.arange(size, device=self.device) + self.clock - size) % self.capacity
            legal = self.valid_length[:, slots] >= h
            legal[:, :h-1] = False
            cumulative = legal.cumsum(1, dtype=torch.int32)
            self.index[h] = (cumulative, torch.where(cumulative[:, -1] > 0)[0])
        return self.index[h]

    def draw(self, h, batch):
        cumulative, feasible = self.positions(h)
        lane = feasible[torch.randint(len(feasible), (batch,), device=self.device)]
        rank = (torch.rand(batch, device=self.device) * cumulative[lane, -1]).long() + 1
        # Binary search directly in the selected lanes without replicating rows.
        lo, hi = torch.zeros_like(rank), torch.full_like(rank, cumulative.shape[1]-1)
        for _ in range(cumulative.shape[1].bit_length()):
            mid = (lo + hi) // 2
            right = cumulative[lane, mid] < rank
            lo, hi = torch.where(right, mid + 1, lo), torch.where(right, hi, mid)
        end = self.clock - cumulative.shape[1] + lo
        if self.receipt is not None:
            self.receipt.append(torch.stack((lane, end-h+1), 1).cpu().numpy())
        return lane, end

    def get(self, lane, times, keys):
        slots = times % self.capacity
        page_ids = slots // self.page_size
        offsets = slots % self.page_size
        result = {}
        for page in torch.unique(page_ids).tolist():
            mask = page_ids == page
            for key in keys:
                values = self.pages[page][key][offsets[mask], lane[mask]]
                if key not in result:
                    result[key] = values.new_empty((*times.shape, *values.shape[1:]))
                result[key][mask] = values
        return result

    def windows(self, h, batch):
        lane, end = self.draw(h, batch)
        t = end[:, None] + torch.arange(1-h, 1, device=self.device)
        records = self.get(lane[:, None].expand_as(t), t, ('state', 'action'))
        last = self.get(lane, end, ('next_state', 'sim_ctx'))
        states = torch.cat((records['state'], last['next_state'][:, None]), 1)
        actions = torch.cat((records['action'], records['action'][:, -1:]), 1)
        return TensorDict(dict(state=states, action=actions,
                               sim_ctx=last['sim_ctx'][:, None].expand(-1, h+1, -1)),
                          batch_size=(batch, h+1))

    def initial(self, batch):
        lanes, t = self.draw(1, batch)
        return TensorDict(self.get(lanes, t, ('state', 'prev_action', 'sim_ctx', 'history',
                                               'motion_time', 'episode')), batch_size=(batch,))
