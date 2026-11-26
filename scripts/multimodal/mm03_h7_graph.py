"""Fixed-shape H7 loss and backward with the original eager optimizer and sampler."""
import torch

from scripts.multimodal.train_wm import physical_loss


class H7Backward:
    # Only these observed tensors are consumed by physical_loss.
    fields = ("history", "previous_history", "vision", "o", "prev_contact", "p", "a", "prev", "contact", "fresh")

    def __init__(self, model):
        self.model = model
        self.stream = torch.cuda.Stream(device=next(model.parameters()).device)
        self.warm = 0
        self.graph = None
        self.static = {}
        self.replays = 0
        self.disabled = False
        self.check = None
        self.extra_gradient_evaluations = 0

    def eager(self, batch):
        self.model.zero_grad(set_to_none=True)
        loss = physical_loss(self.model,batch)
        loss.backward()
        return loss

    def capture(self, batch):
        # Keep an eager gradient from this actual batch until capture passes its
        # check. The caller makes exactly one Adam update for the batch.
        reference = self.eager(batch).detach()
        gradients = [p.grad for p in self.model.parameters()]
        self.extra_gradient_evaluations += 1
        try:
            self.static = {k: batch[k].clone() for k in self.fields}
            self.model.zero_grad(set_to_none=True)
            self.graph = torch.cuda.CUDAGraph()
            with torch.cuda.graph(self.graph, stream=self.stream, capture_error_mode="thread_local"):
                self.loss = physical_loss(self.model, self.static)
                self.loss.backward()
            self.graph.replay()
            self.replays += 1
            loss_error = (reference - self.loss).abs().item()
            grad_error = torch.stack([(p.grad-g).abs().amax() for p,g in
                                      zip(self.model.parameters(), gradients, strict=True)]).amax().item()
            self.check = dict(loss_max_abs=loss_error, gradient_max_abs=grad_error)
            if loss_error==0. and grad_error==0.:
                return self.loss
        except torch.OutOfMemoryError as err:
            self.check = dict(fallback="CUDA graph allocation", error=str(err))
        for param, grad in zip(self.model.parameters(), gradients, strict=True):
            param.grad = grad
        self.disabled = True
        self.static.clear()
        self.graph = None
        return reference

    def backward(self, batch):
        if self.disabled:
            return self.eager(batch).detach()
        current = torch.cuda.current_stream(self.stream.device)
        self.stream.wait_stream(current)
        with torch.cuda.stream(self.stream):
            for name in self.fields:
                batch[name].record_stream(self.stream)
            if self.warm<2:
                # Grad accumulators and library handles keep the capture stream for this model.
                loss = self.eager(batch).detach()
                self.warm += 1
            elif self.graph is None:
                loss = self.capture(batch)
            else:
                for key, dest in self.static.items():
                    if dest.shape != batch[key].shape or dest.dtype != batch[key].dtype:
                        raise ValueError(f"H7 batch changed at field {key}")
                    dest.copy_(batch[key])
                self.graph.replay()
                self.replays += 1
                loss = self.loss
        current.wait_stream(self.stream)
        return loss.detach()
