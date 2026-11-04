"""进度小鱼的单元测试。

原则：不依赖真实终端。用假的 stream 控制 isatty 与输出捕获；
动画线程只做一次短促的冒烟，其余直接调内部方法，避免时序抖动。
"""
import io
import time

import install_manifest as im


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


def test_disabled_swimmer_is_silent():
    stream = FakeTTY()
    fish = im._Swimmer(stream=stream, enabled=False)
    fish.start()
    fish.message("hello")
    fish.stop()
    assert stream.getvalue() == "hello\n"


def test_message_erases_fish_line_before_writing():
    stream = FakeTTY()
    fish = im._Swimmer(stream=stream, enabled=True)
    fish._drawn = True            # 假装鱼已经画在最后一行
    fish.message("hello")
    out = stream.getvalue()
    assert out.startswith("\r"), "打印消息前必须先回车到行首"
    assert "hello\n" in out
    # 擦除段由 \r + 空格 + \r 组成
    erase = out[: out.index("hello")]
    assert erase.count("\r") == 2
    assert erase.strip("\r").strip() == ""


def test_frame_moves_forward_then_flips():
    fish = im._Swimmer(width=20, enabled=False)
    fish._pos, fish._dir = 0, 1
    first = fish._frame()
    fish._pos = 5
    moved = fish._frame()
    assert first != moved
    assert im._Swimmer.FISH_RIGHT in first

    fish._dir = -1
    assert im._Swimmer.FISH_LEFT in fish._frame()


def test_frame_width_is_stable():
    fish = im._Swimmer(width=40, enabled=False)
    for pos in (0, 7, 20, 30):
        fish._pos = pos
        assert len(fish._frame()) == 40


def test_animation_thread_draws_water():
    stream = FakeTTY()
    fish = im._Swimmer(width=24, stream=stream, enabled=True)
    fish.TICK = 0.01
    fish.start()
    time.sleep(0.06)
    fish.stop()
    out = stream.getvalue()
    assert "\r" in out
    assert im._Swimmer.WATER in out
    assert im._Swimmer.FISH_RIGHT in out or im._Swimmer.FISH_LEFT in out
    # stop() 之后最后一行应当被清空
    assert out.endswith("\r")
