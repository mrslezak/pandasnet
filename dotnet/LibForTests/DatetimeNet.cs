using System;
using System.Collections.Generic;
using System.Linq;

namespace LibForTests
{
    public class DatetimeNet
    {
        public static DateTime DateTimePassThrough(DateTime x) => x;

        public static TimeSpan TimeSpanPassThrough(TimeSpan x) => x;

        public static DateTime FromTicks(long ticks, DateTimeKind kind) => new DateTime(ticks, kind);
        public static DateTime[] ArrayFromTicks(long[] ticks, DateTimeKind kind) => ticks.Select(p => new DateTime(p, kind)).ToArray();
        public static IReadOnlyList<DateTime> ListFromTicks(long[] ticks, DateTimeKind kind) => ticks.Select(p => new DateTime(p, kind)).ToList();

        public static DateTime[] ArrayPassThrough(DateTime[] x) => x;
        public static IReadOnlyList<DateTime> ListPassThrough(IEnumerable<DateTime> x) => x.ToList();
        public static string Kind(DateTime x) => x.Kind.ToString();
        public static long Ticks(DateTime x) => x.Ticks;
    }
}
