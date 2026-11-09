using System;

namespace LibForTests
{
    public class NumpyNet
    {
        public static int Int32ScalarPassThrough(int value) => value;
        public static bool[] OneDimensionBooleanArray(bool[] array) => array;
        public static sbyte[] OneDimensionInt8Array(sbyte[] array) => array;
        public static short[] OneDimensionInt16Array(short[] array) => array;
        public static int[] OneDimensionInt32Array(int[] array) => array;
        public static long[] OneDimensionInt64Array(long[] array) => array;

        public static byte[] OneDimensionUInt8Array(byte[] array) => array;
        public static ushort[] OneDimensionUInt16Array(ushort[] array) => array;
        public static uint[] OneDimensionUInt32Array(uint[] array) => array;
        public static ulong[] OneDimensionUInt64Array(ulong[] array) => array;

        public static float[] OneDimensionFloat32Array(float[] array) => array;
        public static double[] OneDimensionFloat64Array(double[] array) => array;

        public static string[] OneDimensionStringArray(string[] array) => array;
        public static DateTime[] OneDimensionDateTimeArray(DateTime[] array) => array;
        public static TimeSpan[] OneDimensionTimeSpanArray(TimeSpan[] array) => array;

        public int[] InstanceInt32Array(int[] array) => array;

        public static int[] AddInt32Arrays(int[] left, int[] right)
        {
            if (left.Length != right.Length)
                throw new ArgumentException("Array lengths must match.");

            var result = new int[left.Length];
            for (var i = 0; i < left.Length; i++)
                result[i] = left[i] + right[i];
            return result;
        }

        public static string MixedArguments(int[] values, int multiplier, string label)
        {
            var result = new string[values.Length];
            for (var i = 0; i < values.Length; i++)
                result[i] = (values[i] * multiplier).ToString();
            return label + ":" + string.Join(",", result);
        }

        public static int[] NullableInt32Array(int[] array) => array;
        public static int[] ReturnNullInt32Array() => null;

        public static string Overloaded(int[] array) => "Int32[]";
        public static string Overloaded(double[] array) => "Double[]";
        public static string Overloaded(string value) => "String";
    }
}
