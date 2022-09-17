# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Microbenchmarks for JAX `api` functions."""

import functools
import operator

import google_benchmark
import jax
from jax import lax
from jax._src import test_util as jtu
from jax._src import config as jax_config
from jax.experimental import sparse
from jax._src.api_util import shaped_abstractify  # technically not an api fn
from jax._src.ad_checkpoint import checkpoint  # new jax.remat implementation
from jax._src.lib import xla_client as xc
from jax.interpreters import pxla
from jax.experimental import array
from jax.experimental import maps
from jax.experimental import sharding
from jax.experimental import pjit as pjit_lib
import jax.numpy as jnp
import numpy as np


partial = functools.partial

def required_devices(num_devices_required):
  """Helper to skip benchmarks that require more devices."""
  def helper1(f):
    @functools.wraps(f)
    def helper2(state):
      if jax.device_count() < num_devices_required:
        state.skip_with_error(f"requires {num_devices_required} devices")
        return
      return f(state)
    return helper2
  return helper1

def swap(a, b):
  return b, a


@google_benchmark.register
def eager_unary_dispatch(state):
  a = jax.device_put(1)
  lax.neg(a)
  while state:
    lax.neg(a)


@google_benchmark.register
def eager_unary(state):
  a = jax.device_put(1)
  lax.neg(a).block_until_ready()
  while state:
    lax.neg(a).block_until_ready()


@google_benchmark.register
def eager_binary_dispatch(state):
  a = jax.device_put(1)
  b = jax.device_put(2)
  lax.add(a, b)
  while state:
    lax.add(a, b)


@google_benchmark.register
def eager_binary(state):
  a = jax.device_put(1)
  b = jax.device_put(2)
  lax.add(a, b).block_until_ready()
  while state:
    lax.add(a, b).block_until_ready()


@google_benchmark.register
def jit_trivial_dispatch(state):
  """Benchmarks only the duration for jitted_f to return the future."""
  f = jax.jit(swap)
  a, b = f(1, 2)
  x = f(a, b)
  while state:
    x = f(a, b)
  x[0].block_until_ready()


@google_benchmark.register
def jit_trivial(state):
  f = jax.jit(swap)
  a, b = f(1, 2)
  f(a, b)

  while state:
    c, d = f(a, b)
    c.block_until_ready()
    d.block_until_ready()


@google_benchmark.register
def jit_simple_dispatch(state):
  a = jax.device_put(1)
  b = jax.device_put(2)
  f = jax.jit(operator.add)
  f(a, b)

  while state:
    f(a, b)


@google_benchmark.register
def jit_simple(state):
  a = jax.device_put(1)
  b = jax.device_put(2)
  f = jax.jit(operator.add)
  f(a, b)

  while state:
    f(a, b).block_until_ready()

@google_benchmark.register
def jit_simple_dispatch_array(state):
  with jax_config.jax_array(True):
    a = jax.device_put(1)
    b = jax.device_put(2)
    f = jax.jit(operator.add)
    f(a, b)

    while state:
      f(a, b)


@google_benchmark.register
def jit_simple_array(state):
  with jax_config.jax_array(True):
    a = jax.device_put(1)
    b = jax.device_put(2)
    f = jax.jit(operator.add)
    f(a, b)

    while state:
      f(a, b).block_until_ready()


@google_benchmark.register
def jit_small_matmul(state):
  x = np.random.uniform(size=(2, 2)).astype(np.float32)
  x = jax.device_put(x)

  f = jax.jit(lambda x: jnp.dot(x, x))
  f(x).block_until_ready()

  while state:
    f(x).block_until_ready()


@google_benchmark.register
def jit_big_matmul(state):
  x = np.random.uniform(size=(100, 100)).astype(np.float32)
  x = jax.device_put(x)

  f = jax.jit(lambda x: jnp.dot(x, x))
  f(x).block_until_ready()

  while state:
    f(x).block_until_ready()


def jit_simple_many_args_dispatch(n, state):
  args = [jax.device_put(i) for i in range(n)]
  f = jax.jit(lambda xs: functools.reduce(operator.add, xs))
  x = f(args)
  x.block_until_ready()

  while state:
    x = f(args)
  x.block_until_ready()

def jit_simple_many_args(n, state):
  args = [jax.device_put(i) for i in range(n)]
  f = jax.jit(lambda xs: functools.reduce(operator.add, xs))
  f(args).block_until_ready()

  while state:
    f(args).block_until_ready()

def jit_simple_pruned_args_dispatch(n, state):
  args = [jax.device_put(i) for i in range(n)]
  f = jax.jit(lambda *xs: xs[0] + 1)
  x = f(*args)
  x.block_until_ready()

  while state:
    x = f(*args)
  x.block_until_ready()


def jit_simple_pruned_args(n, state):
  args = [jax.device_put(i) for i in range(n)]
  f = jax.jit(lambda *xs: xs[0] + 1)
  x = f(*args)
  x.block_until_ready()

  while state:
    f(*args).block_until_ready()

benchmarks = []
for n in [10, 100, 1000, 2000]:
  benchmarks += [
      google_benchmark.register(partial(jit_simple_many_args_dispatch, n),
                                name=f"jit_simple_many_args_dispatch_{n}"),
      google_benchmark.register(partial(jit_simple_many_args, n),
                                name=f"jit_simple_many_args_{n}"),
      google_benchmark.register(partial(jit_simple_pruned_args_dispatch, n),
                                name=f"jit_simple_pruned_args_dispatch_{n}"),
      google_benchmark.register(partial(jit_simple_pruned_args, n),
                                name=f"jit_simple_pruned_args_{n}")
  ]


@google_benchmark.register
def jit_dispatch_without_transfer(state):
  # We pick up a realistic input. 224 is usual for classification and 128 a
  # TPU-friendly batch-size.
  imgs = np.ones((128, 224, 224), np.float32)
  imgs = jax.device_put(imgs)

  f = jax.jit(lambda x: x+1)
  f(imgs)

  while state:
    f(imgs)


@google_benchmark.register
def jit_dispatch_with_transfer(state):
  imgs = np.ones((128, 224, 224), np.float32)

  f = jax.jit(lambda x: x+1)
  f(imgs).block_until_ready()

  while state:
    x = f(imgs)
  x.block_until_ready()


@google_benchmark.register
@google_benchmark.option.arg_name('jax_array')
@google_benchmark.option.arg(True)
@google_benchmark.option.arg(False)
@required_devices(2)
def pmap_trivial_2_devices(state):
  with jax_config.jax_array(state.range(0)):
    f = jax.pmap(swap)
    a, b = f(jnp.array([1, 2]), jnp.array([3, 4]))

    while state:
      c, d = f(a, b)
      c.block_until_ready()
      d.block_until_ready()


@google_benchmark.register
@google_benchmark.option.arg_name('jax_array')
@google_benchmark.option.arg(True)
@google_benchmark.option.arg(False)
@required_devices(8)
def pmap_trivial_dispatch_8_devices(state):
  with jax_config.jax_array(state.range(0)):
    f = jax.pmap(swap)
    a, b = f(jnp.array([1, 2, 3, 4, 5, 6, 7, 8]),
             jnp.array([2, 3, 4, 5, 6, 7, 8, 9]))

    while state:
      a, b = f(a, b)


@google_benchmark.register
@google_benchmark.option.arg_name('jax_array')
@google_benchmark.option.arg(True)
@google_benchmark.option.arg(False)
@required_devices(8)
def pmap_trivial_8_devices(state):
  with jax_config.jax_array(state.range(0)):
    f = jax.pmap(swap)
    a, b = f(jnp.array([1, 2, 3, 4, 5, 6, 7, 8]),
             jnp.array([2, 3, 4, 5, 6, 7, 8, 9]))

    while state:
      c, d = f(a, b)
      c.block_until_ready()
      d.block_until_ready()


@google_benchmark.register
@google_benchmark.option.arg_name('jax_array')
@google_benchmark.option.arg(True)
@google_benchmark.option.arg(False)
@required_devices(2)
def pmap_simple_2_devices(state):
  with jax_config.jax_array(state.range(0)):
    f = jax.pmap(lambda a, b: (a + b, a - b))
    a, b = f(jnp.array([1, 2]), jnp.array([3, 4]))

    while state:
      c, d = f(a, b)
      c.block_until_ready()
      d.block_until_ready()


@google_benchmark.register
@google_benchmark.option.arg_name('jax_array')
@google_benchmark.option.arg(True)
@google_benchmark.option.arg(False)
@required_devices(8)
def pmap_simple_dispatch_8_devices(state):
  with jax_config.jax_array(state.range(0)):
    f = jax.pmap(lambda a, b: (a + b, a - b))
    a, b = f(jnp.array([1, 2, 3, 4, 5, 6, 7, 8]),
             jnp.array([2, 3, 4, 5, 6, 7, 8, 9]))

    while state:
      a, b = f(a, b)


@google_benchmark.register
@google_benchmark.option.arg_name('jax_array')
@google_benchmark.option.arg(True)
@google_benchmark.option.arg(False)
@required_devices(8)
def pmap_simple_8_devices(state):
  with jax_config.jax_array(state.range(0)):
    f = jax.pmap(lambda a, b: (a + b, a - b))
    a, b = f(jnp.array([1, 2, 3, 4, 5, 6, 7, 8]),
             jnp.array([2, 3, 4, 5, 6, 7, 8, 9]))

    while state:
      c, d = f(a, b)
      c.block_until_ready()
      d.block_until_ready()


@google_benchmark.register
@google_benchmark.option.arg_name('jax_array')
@google_benchmark.option.arg(True)
@google_benchmark.option.arg(False)
@required_devices(8)
def pmap_simple_dispatch_8_devices_100_args(state):
  with jax_config.jax_array(state.range(0)):
    f = jax.pmap(lambda *args: args[1:] + (args[0] + 1,))
    args = []
    for i in range(100):
      args.append(jnp.array(list(range(i, i+8))))

    args = f(*args)

    while state:
      args = f(*args)


@google_benchmark.register
@google_benchmark.option.arg_name('jax_array')
@google_benchmark.option.arg(True)
@google_benchmark.option.arg(False)
@required_devices(8)
def pmap_simple_8_devices_100_args(state):
  with jax_config.jax_array(state.range(0)):
    f = jax.pmap(lambda *args: args[1:] + (args[0] + 1,))
    args = []
    for i in range(100):
      args.append(jnp.array(list(range(i, i+8))))

    # Warmup loop.
    out = f(*args)

    while state:
      out = f(*args)
      jax.tree_util.tree_map(lambda x: x.block_until_ready(), out)


def _run_sda_index_bench(state, num_devices):
  x = jax.pmap(jnp.sin)(jnp.arange(num_devices))
  jax.device_get(x)
  while state:
    for i in range(num_devices):
      _ = x[i]


@google_benchmark.register
@required_devices(1)
def sda_index_1(state):
  _run_sda_index_bench(state, 1)


@google_benchmark.register
@required_devices(2)
def sda_index_2(state):
  _run_sda_index_bench(state, 2)


@google_benchmark.register
@required_devices(8)
def sda_index_8(state):
  _run_sda_index_bench(state, 8)


def _sparse_bcoo_fromdense(state, jit: bool = False, compile: bool = False):
  shape = (2000, 2000)
  nse = 10000
  size = np.prod(shape)
  rng = np.random.RandomState(1701)
  data = rng.randn(nse)
  indices = np.unravel_index(
      rng.choice(size, size=nse, replace=False), shape=shape)
  mat = jnp.zeros(shape).at[indices].set(data)

  f = sparse.BCOO.fromdense
  if compile or jit:
    # Note: nse must be specified for JIT.
    f = jax.jit(partial(f, nse=nse))

  if compile:
    while state:
      f.lower(mat).compile()
  else:
    f(mat).block_until_ready()
    while state:
      f(mat).block_until_ready()


@google_benchmark.register
def sparse_bcoo_fromdense(state):
  return _sparse_bcoo_fromdense(state)


@google_benchmark.register
def sparse_bcoo_fromdense_jit(state):
  return _sparse_bcoo_fromdense(state, jit=True)


@google_benchmark.register
def sparse_bcoo_fromdense_compile(state):
  return _sparse_bcoo_fromdense(state, compile=True)


def _sparse_bcoo_todense(state, jit: bool = False, compile: bool = False):
  shape = (2000, 2000)
  nse = 10000
  size = np.prod(shape)
  rng = np.random.RandomState(1701)
  data = rng.randn(nse)
  indices = np.unravel_index(
      rng.choice(size, size=nse, replace=False), shape=shape)
  mat = sparse.BCOO((jnp.array(data), jnp.column_stack(indices)), shape=shape)

  f = lambda mat: mat.todense()
  if jit or compile:
    f = jax.jit(f)

  if compile:
    while state:
      f.lower(mat).compile()
  else:
    f(mat).block_until_ready()
    while state:
      f(mat).block_until_ready()


@google_benchmark.register
def sparse_bcoo_todense(state):
  return _sparse_bcoo_todense(state)


@google_benchmark.register
def sparse_bcoo_todense_jit(state):
  return _sparse_bcoo_todense(state, jit=True)


@google_benchmark.register
def sparse_bcoo_todense_compile(state):
  return _sparse_bcoo_todense(state, compile=True)


def _sparse_bcoo_matvec(state, jit: bool = False, compile: bool = False):
  shape = (2000, 2000)
  nse = 10000
  key = jax.random.PRNGKey(1701)
  mat = sparse.random_bcoo(key, nse=nse, shape=shape, dtype=jnp.float32,
                           indices_dtype=jnp.int32, sorted_indices=True)
  vec = jax.random.uniform(key, shape=(shape[1],), dtype=jnp.float32)

  f = lambda mat, vec: mat @ vec
  if jit or compile:
    f = jax.jit(f)

  if compile:
    while state:
      f.lower(mat, vec).compile()
  else:
    f(mat, vec).block_until_ready()
    while state:
      f(mat, vec).block_until_ready()


@google_benchmark.register
def sparse_bcoo_matvec(state):
  return _sparse_bcoo_matvec(state)


@google_benchmark.register
def sparse_bcoo_matvec_jit(state):
  return _sparse_bcoo_matvec(state, jit=True)


@google_benchmark.register
def sparse_bcoo_matvec_compile(state):
  return _sparse_bcoo_matvec(state, compile=True)


@google_benchmark.register
@google_benchmark.option.unit(google_benchmark.kMillisecond)
def bench_shaped_abstractify(state):
  device, *_ = jax.devices()
  args = [jax.device_put_replicated(1, [device])] * 1000
  while state:
    _ = [shaped_abstractify(x) for x in args]


@google_benchmark.register
@google_benchmark.option.unit(google_benchmark.kMicrosecond)
def bench_are_op_shardings_equal(state):
  op1 = xc.OpSharding()
  op1.type = xc.OpSharding.Type.OTHER
  op1.tile_assignment_dimensions = [4, 192, 16]
  op1.tile_assignment_devices = list(range(12288))

  op2 = xc.OpSharding()
  op2.type = xc.OpSharding.Type.OTHER
  op2.tile_assignment_dimensions = [4, 192, 16]
  op2.tile_assignment_devices = list(range(12288))

  while state:
    pxla.are_op_shardings_equal(op1, op2)


@google_benchmark.register
@google_benchmark.option.unit(google_benchmark.kMillisecond)
def bench_pjit_check_aval_sharding(state):
  mesh = jtu.create_global_mesh((4, 2), ('x', 'y'))
  s = sharding.MeshPspecSharding(mesh, pxla.PartitionSpec('x', 'y'))
  aval = jax.ShapedArray((8, 2), np.int32)

  while state:
    pjit_lib.pjit_check_aval_sharding([s] * 100, [aval] * 100, 'benchmark', False)


@google_benchmark.register
@google_benchmark.option.unit(google_benchmark.kMillisecond)
def bench_remat_eager_retracing_overheads(state):
  def double_compose(f):
    return lambda x: f(f(x))

  f = jnp.sin
  for _ in range(6):
    f = double_compose(f)
  f = double_compose(checkpoint(f))

  while state:
    y, _ = jax.vjp(f, 3.)
  y.block_until_ready()

@google_benchmark.register
@google_benchmark.option.unit(google_benchmark.kMillisecond)
def bench_remat_eager_retracing_overheads_static_argnums(state):
  def double_compose(f):
    return lambda x, y: f(f(x, y), y)

  f = lambda x, _: jnp.sin(x)
  for _ in range(6):
    f = double_compose(f)
  f = double_compose(checkpoint(f, static_argnums=(1,)))

  while state:
    y, _ = jax.vjp(f, 3., True)
  y.block_until_ready()


@google_benchmark.register
@google_benchmark.option.unit(google_benchmark.kMillisecond)
def bench_slicing_compilation(state):
  x = jnp.arange(3)
  while state:
    jax.jit(lambda x: (x[0], x[1], x[2])).lower(x).compile()

@google_benchmark.register
@google_benchmark.option.unit(google_benchmark.kMillisecond)
def bench_slicing_compilation2(state):
  x = jnp.arange(3)
  while state:
    jax.jit(lambda x: (x[:1], x[1:2], x[2:3])).lower(x).compile()


def pjit_simple_benchmark(state, num_devices):
  spec = pjit_lib.PartitionSpec('x')
  mesh = maps.Mesh(np.array(jax.devices()[:num_devices]), ('x',))
  s = sharding.MeshPspecSharding(mesh, spec)
  x = np.arange(jax.device_count()).astype(np.float32)
  x = array.make_array_from_callback(x.shape, s, x.__getitem__)

  x = [x for i in range(state.range(1))]

  prev_state = jax_config.FLAGS.experimental_cpp_pjit
  jax_config.FLAGS.experimental_cpp_pjit = state.range(0)

  in_axis_resources = sharding.MeshPspecSharding(mesh, spec)
  out_axis_resources = sharding.MeshPspecSharding(mesh, spec)

  f = pjit_lib.pjit(
      lambda x: jax.tree_map(lambda x: x + 1, x),
      in_axis_resources=in_axis_resources,
      out_axis_resources=out_axis_resources)

  x = f(x)

  while state:
    x = f(x)

  jax_config.FLAGS.experimental_cpp_pjit = prev_state


@google_benchmark.register
@google_benchmark.option.arg_names(['cpp_pjit', 'num_args'])
@google_benchmark.option.args([False, 1])
@google_benchmark.option.args([False, 10])
@google_benchmark.option.args([False, 100])
@google_benchmark.option.args([True, 1])
@google_benchmark.option.args([True, 10])
@google_benchmark.option.args([True, 100])
@jax_config.jax_array(True)
def pjit_simple_1_device(state):
  pjit_simple_benchmark(state, num_devices=1)


@google_benchmark.register
@google_benchmark.option.arg_names(['cpp_pjit', 'num_args'])
@google_benchmark.option.args([False, 1])
@google_benchmark.option.args([False, 10])
@google_benchmark.option.args([False, 100])
@google_benchmark.option.args([True, 1])
@google_benchmark.option.args([True, 10])
@google_benchmark.option.args([True, 100])
@required_devices(4)
@jax_config.jax_array(True)
def pjit_simple_4_devices(state):
  pjit_simple_benchmark(state, num_devices=4)


if __name__ == "__main__":
  google_benchmark.main()
