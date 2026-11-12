using System;

namespace PandasNet
{
    /// <summary>Row-major (C order) copies between flat vectors and multi-dimensional arrays.</summary>
    public static class ArrayShape
    {
        // Declared as Array so pythonnet returns the CLR array instead of encoding it to NumPy.
        public static Array Reshape<T>(T[] source, int[] lengths)
        {
            if (source == null) throw new ArgumentNullException(nameof(source));
            if (lengths == null || lengths.Length == 0) throw new ArgumentException("At least one dimension is required.", nameof(lengths));

            long size = 1;
            foreach (var length in lengths)
            {
                if (length < 0) throw new ArgumentOutOfRangeException(nameof(lengths), "Dimensions cannot be negative.");
                size *= length;
            }
            if (size != source.Length)
                throw new ArgumentException($"Cannot reshape {source.Length} elements into {string.Join("x", lengths)}.");

            switch (lengths.Length)
            {
                case 1:
                    return (T[])source.Clone();
                case 2:
                {
                    var result = new T[lengths[0], lengths[1]];
                    var p = 0;
                    for (var i = 0; i < lengths[0]; i++)
                        for (var j = 0; j < lengths[1]; j++)
                            result[i, j] = source[p++];
                    return result;
                }
                case 3:
                {
                    var result = new T[lengths[0], lengths[1], lengths[2]];
                    var p = 0;
                    for (var i = 0; i < lengths[0]; i++)
                        for (var j = 0; j < lengths[1]; j++)
                            for (var k = 0; k < lengths[2]; k++)
                                result[i, j, k] = source[p++];
                    return result;
                }
                case 4:
                {
                    var result = new T[lengths[0], lengths[1], lengths[2], lengths[3]];
                    var p = 0;
                    for (var i = 0; i < lengths[0]; i++)
                        for (var j = 0; j < lengths[1]; j++)
                            for (var k = 0; k < lengths[2]; k++)
                                for (var l = 0; l < lengths[3]; l++)
                                    result[i, j, k, l] = source[p++];
                    return result;
                }
                default:
                {
                    var result = Array.CreateInstance(typeof(T), lengths);
                    var index = new int[lengths.Length];
                    for (var p = 0; p < source.Length; p++)
                    {
                        result.SetValue(source[p], index);
                        for (var d = index.Length - 1; d >= 0 && ++index[d] == lengths[d]; d--)
                            index[d] = 0;
                    }
                    return result;
                }
            }
        }

        public static T[] Flatten<T>(Array source)
        {
            if (source == null) throw new ArgumentNullException(nameof(source));

            var result = new T[source.Length];
            var p = 0;
            switch (source)
            {
                case T[] vector:
                    Array.Copy(vector, result, vector.Length);
                    break;
                case T[,] matrix:
                    foreach (var item in matrix) result[p++] = item;
                    break;
                case T[,,] cube:
                    foreach (var item in cube) result[p++] = item;
                    break;
                case T[,,,] hypercube:
                    foreach (var item in hypercube) result[p++] = item;
                    break;
                default:
                    foreach (T item in source) result[p++] = item;
                    break;
            }
            return result;
        }
    }
}
