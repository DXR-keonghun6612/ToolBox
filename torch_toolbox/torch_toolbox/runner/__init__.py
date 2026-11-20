"""runner - torch 학습, 평가, export 실행. 설정은 `config`, 실행 바탕은 `runner`, 일은 `job`, 조립은 `assembler`.

진입은 python_toolbox `Runner.From_argv` - 사용처가 `Torch_Runner` 를 상속해 `config` 타입과 `JOB_REGISTRY` 를 선언.
모듈까지 적어 import - 여기서 다시 내보내지 않음.
"""
