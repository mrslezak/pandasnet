using System;
    
namespace PandasNet
{
    /// <summary>How DateTimeKind.Local values are returned to Python.</summary>
    public enum LocalDateTimePolicy
    {
        /// <summary>Keep the local wall-clock value (naive datetime / datetime64).</summary>
        WallClock,
        /// <summary>Convert to UTC (aware UTC datetime / datetime64 in UTC).</summary>
        Utc,
    }

    public static class Time
    {
        public static LocalDateTimePolicy LocalPolicy { get; set; } = LocalDateTimePolicy.WallClock;

        // Utc values are always returned in UTC; Unspecified values always keep their wall-clock value.
        public static bool EncodesAsUtc(DateTime x)
            => x.Kind == DateTimeKind.Utc || (x.Kind == DateTimeKind.Local && LocalPolicy == LocalDateTimePolicy.Utc);

        public static readonly DateTime Origin = new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc);
        public static readonly long OriginTicks = Origin.Ticks;

        public static readonly long KindLocalTicks = (long)DateTimeKind.Local << 62;
        public static readonly long KindUtcTicks = (long)DateTimeKind.Utc << 62;

        public const double TICKS_BY_NS = 0.01;
        public const long TICKS_BY_US = 10;
        public const long TICKS_BY_MS = 1000 * TICKS_BY_US;
        public const long TICKS_BY_SEC = 1000 * TICKS_BY_MS;
        public const long TICKS_BY_MIN = 60 * TICKS_BY_SEC;
        public const long TICKS_BY_HOUR = 60 * TICKS_BY_MIN;
        public const long TICKS_BY_DAY = 24 * TICKS_BY_HOUR;
        public const long TICKS_BY_WEEK = 7 * TICKS_BY_DAY;
    }
}
