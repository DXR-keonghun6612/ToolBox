from . import scalar, centroid, scatter

ACCUMULATOR_TYPES = (
    scalar.Scalar_Accumulator | centroid.Centroid_Accumulator
    | scatter.Within_Class_Scatter_Accumulator)
