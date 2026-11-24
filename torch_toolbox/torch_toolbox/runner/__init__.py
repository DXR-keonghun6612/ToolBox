"""runner - torch 학습, 평가, export 실행. 설정은 `config`, 일은 `job`, 조립은 `assembler`.

진입은 python_toolbox `Launcher.From_argv` - 사용처가 `Launcher` 를 상속해 `JOB_REGISTRY` 를 선언, job 설정은 meta 에서 `CONFIGS` 로.
모듈까지 적어 import - 여기서 다시 내보내지 않음.
"""
