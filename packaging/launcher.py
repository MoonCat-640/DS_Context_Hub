"""打包版的入口。正常启动时打开 Qt 窗口，自检模式把结果写到指定文件。"""

import sys
from pathlib import Path


def main():
    # 分支内导入让发行自检与用户双击启动共用一个可执行文件，各自调用对应入口。
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from smoke_test import run

        return run(Path(sys.argv[2]))

    from ds_context_hub.ui import main as run_app

    run_app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
