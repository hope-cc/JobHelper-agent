from dataclasses import dataclass
@dataclass
class SubmitResult:
    output : str
    is_error : bool = False