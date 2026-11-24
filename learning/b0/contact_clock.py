"""Clocks shared by the contact plant, GenCoord and the recorded references."""
from dataclasses import dataclass
from math import isclose, isfinite


@dataclass(frozen=True)
class ContactClock:
    physics_dt: float
    servo_dt = .002
    policy_dt = .020
    reference_ticks = 10

    def __post_init__(self):
        if not isfinite(self.physics_dt) or self.physics_dt <= 0:
            raise ValueError("Expected a finite positive physics timestep")
        n = self.servo_stride
        if n < 1 or not isclose(n * self.physics_dt, self.servo_dt, abs_tol=1e-12, rel_tol=0):
            raise ValueError("The physics timestep must divide the recorded 2 ms servo period")

    @property
    def servo_stride(self):
        return round(self.servo_dt / self.physics_dt)

    @property
    def policy_steps(self):
        return self.reference_ticks * self.servo_stride

    @property
    def substep_coeff(self):
        n = self.policy_steps
        return (n + 1) / (2 * n)

    def metadata(self):
        return dict(physics_dt=self.physics_dt, servo_dt=self.servo_dt, policy_dt=self.policy_dt,
                    physics_steps_per_policy=self.policy_steps, physical_prefix_steps=10*self.policy_steps,
                    substep_coeff=self.substep_coeff, servo_bias_delay_s=self.servo_dt,
                    servo_bias_sample="interval-start bias from preceding 2 ms solve",
                    contact_site_time="solve start", qpos_qvel_time="integrated end",
                    judge_time="after solve at interval end")
