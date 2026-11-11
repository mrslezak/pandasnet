using Python.Runtime;
using System;

namespace PandasNet
{
    public static class DateTimeCodec
    {
        public static void Initialize(Codecs codecs)
        {
            // .Net -> Python
            codecs.Register<DateTime>(EncodeDateTime);
            codecs.Register<TimeSpan>(EncodeTimeSpan);

            // Python -> .Net
            codecs.Register("<class 'datetime.date'>", DecodeDate);
            codecs.Register("<class 'datetime.datetime'>", DecodeDateTime);
            codecs.Register("<class 'datetime.time'>", DecodeTime);
            codecs.Register("<class 'datetime.timedelta'>", DecodeTimeDelta);
        }

        private static PyObject EncodeDateTime(DateTime x)
        {
            using(var scope = Py.CreateScope())
            {
                scope.Import("datetime");
                var tz = string.Empty;
                if (Time.EncodesAsUtc(x))
                {
                    x = x.ToUniversalTime();
                    tz = ", tzinfo=datetime.timezone.utc";
                }
                var microseconds = x.Ticks / 10L % 1000000L;
                scope.Exec($"a = datetime.datetime({x:yyyy, M, d, H, m, s}, {microseconds}{tz})");
                return scope.Get("a");
            }
        }

        private static PyObject EncodeTimeSpan(TimeSpan x)
        {
            using (var scope = Py.CreateScope())
            {
                scope.Import("datetime");
                var microseconds = x.Ticks / 10L % 1000000L;
                scope.Exec($"a = datetime.timedelta(days={x.Days}, hours={x.Hours}, minutes={x.Minutes}, seconds={x.Seconds}, microseconds={microseconds})");
                return scope.Get("a");
            }
        }

        private static DateTime DecodeDate(PyObject py) 
            => new DateTime(
                py.GetAttr("year").As<int>(),
                py.GetAttr("month").As<int>(),
                py.GetAttr("day").As<int>())
                .Date;

        public static DateTime DecodeDateTime(PyObject py)
        {
            var utcDelta = TimeSpan.Zero;
            var kind = DateTimeKind.Local;

            var tz = py.GetAttr("tzinfo");
            if (tz.HasAttr("utcoffset"))
            {
                kind = DateTimeKind.Utc;
                utcDelta = py.InvokeMethod("utcoffset")
                    .DecodeTimeDelta();
            }
            
            var result = new DateTime(
                py.GetAttr("year").As<int>(),
                py.GetAttr("month").As<int>(),
                py.GetAttr("day").As<int>(),
                py.GetAttr("hour").As<int>(),
                py.GetAttr("minute").As<int>(),
                py.GetAttr("second").As<int>(),
                kind);

            // Aware values become the equivalent UTC instant; naive values keep their wall-clock time.
            return result.AddTicks(-utcDelta.Ticks + py.GetAttr("microsecond").As<int>() * 10);
        }

        private static TimeSpan DecodeTime(PyObject py)
        {
            var result = new TimeSpan(
                py.GetAttr("hour").As<int>(),
                py.GetAttr("minute").As<int>(),
                py.GetAttr("second").As<int>());

            return TimeSpan.FromTicks(
                result.Ticks +
                py.GetAttr("microsecond").As<int>() * 10);
        }

        public static TimeSpan DecodeTimeDelta(this PyObject py)
        {
            var days = py.GetAttr("days").As<int>();
            var seconds = py.GetAttr("seconds").As<int>();
            var microseconds = py.GetAttr("microseconds").As<int>();
            var ticks = checked(
                (long)days * Time.TICKS_BY_DAY +
                (long)seconds * Time.TICKS_BY_SEC +
                (long)microseconds * Time.TICKS_BY_US);
            return TimeSpan.FromTicks(ticks);
        }

    }
}
