from typing import Annotated, Literal
import numpy as np
import numpy.typing as npt

Image = Annotated[npt.NDArray[np.uint8], Literal[3, "N", "M"]]
