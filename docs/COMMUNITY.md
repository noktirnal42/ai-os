# Community guide

AI OS is easiest to contribute to when a proposal has a narrow capability,
clear evidence, and a rollback story. Design discussions should name the guest
boundary, the model/runtime assumptions, and the exact acceptance command.

Good first projects include an app with a manifest and test, a new evaluator,
a VM recovery improvement, or a review of the security model. Keep credentials,
model weights, VM disks, and host-specific state out of commits.

Use issues for reproducible bugs and scoped proposals. Use discussions for
architecture questions. Pull requests should stay focused enough that another
contributor can run the same checks locally and in CI.
