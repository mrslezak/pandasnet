using System;
using System.Collections.Generic;
using System.Linq;

namespace LibForTests
{
    public class Item
    {
        public Item(string id, double value)
        {
            Id = id;
            Value = value;
        }

        public string Id { get; }
        public double Value { get; }
    }

    public class CollectionsNet
    {
        // Python -> .Net: generic collection parameters
        public static int CountDates(IEnumerable<DateTime> values) => values.Count();
        public static DateTime LastDate(IReadOnlyList<DateTime> values) => values[values.Count - 1];
        public static double SumEnumerable(IEnumerable<double> values) => values.Sum();
        public static double SumReadOnlyList(IReadOnlyList<double> values) => values.Sum();
        public static double SumList(IList<double> values) => values.Sum();
        public static double SumCollection(ICollection<double> values) => values.Sum();
        public static double SumConcreteList(List<double> values) => values.Sum();
        public static double SumArray(double[] values) => values.Sum();
        public static long SumInt64Enumerable(IEnumerable<long> values) => values.Sum();
        public static TimeSpan TotalDuration(IEnumerable<TimeSpan> values) => values.Aggregate(TimeSpan.Zero, (a, b) => a + b);
        public static string JoinStrings(IEnumerable<string> values) => string.Join(",", values);
        public static string JoinIds(IReadOnlyList<Item> items) => string.Join(",", items.Select(p => p.Id));
        public static int CountNested(IEnumerable<IEnumerable<int>> rows) => rows.Sum(p => p.Count());
        public static int CountNonNull(IEnumerable<DateTime?> values) => values.Count(p => p.HasValue);
        public static double SumDictionary(IDictionary<string, double> values) => values.Values.Sum();
        public static double SumReadOnlyDictionary(IReadOnlyDictionary<DateTime, double> values) => values.Values.Sum();

        public static int AppendToList(IList<double> values)
        {
            values.Add(0.0);
            return values.Count;
        }

        // Overload resolution
        public static string Pick(int value) => "Int32";
        public static string Pick(long value) => "Int64";
        public static string Pick(float value) => "Single";
        public static string Pick(double value) => "Double";
        public static string Pick(bool value) => "Boolean";
        public static string Pick(string value) => "String";
        public static string Pick(DateTime value) => "DateTime";
        public static string Pick(TimeSpan value) => "TimeSpan";

        public static string PickCollection(IEnumerable<DateTime> values) => "IEnumerable<DateTime>";
        public static string PickCollection(IEnumerable<string> values) => "IEnumerable<String>";
        public static string PickCollection(IEnumerable<double> values) => "IEnumerable<Double>";

        public static string Specific(IEnumerable<double> values) => "IEnumerable<Double>";
        public static string Specific(IReadOnlyList<double> values) => "IReadOnlyList<Double>";

        public static string Ambiguous(List<double> values) => "List<Double>";
        public static string Ambiguous(double[] values) => "Double[]";

        public static string TypeName(object value) => value?.GetType().FullName;

        // .Net -> Python: return conversions
        public static IReadOnlyList<double> ReadOnlyDoubles(int count) => Enumerable.Range(0, count).Select(p => p * 0.5).ToList();
        public static IReadOnlyList<double> ReadOnlyDoublesArray(int count) => Enumerable.Range(0, count).Select(p => p * 0.5).ToArray();
        public static IEnumerable<double> LazyDoubles(int count)
        {
            for (var i = 0; i < count; i++)
                yield return i;
        }
        public static IList<int> Int32List() => new List<int> { 1, 2, 3 };
        public static ICollection<long> Int64Collection() => new List<long> { 4, 5 };
        public static List<float> SingleList() => new List<float> { 1.5f, 2.5f };
        public static IEnumerable<bool> Booleans() => new[] { true, false };
        public static IReadOnlyList<DateTime> Dates() => new List<DateTime> { new DateTime(2026, 1, 5), new DateTime(2026, 1, 12) };
        public static IReadOnlyList<string> Names() => new List<string> { "a", "b" };
        public static IReadOnlyList<double?> NullableDoubles() => new List<double?> { 1.0, null };
        public static IEnumerable<double> NullDoubles() => null;
        public static int[] Int32Array() => new[] { 7, 8 };

        public static double[,] Matrix()
            => new double[,] { { 1.0, 2.0, 3.0 }, { 4.0, 5.0, 6.0 } };
        public static int[,] Int32Matrix()
            => new int[,] { { 1, 2 }, { 3, 4 } };

        public static Item MakeItem(string id, double value) => new Item(id, value);
        public static IReadOnlyList<Item> Items() => new List<Item> { new Item("a", 1.0), new Item("b", 2.0) };
        public static IReadOnlyList<IReadOnlyList<double>> Jagged()
            => new List<IReadOnlyList<double>> { new List<double> { 1.0 }, new[] { 2.0, 3.0 } };

        public static Dictionary<string, double[]> PricesById()
            => new Dictionary<string, double[]> { ["a"] = new[] { 1.0, 2.0 }, ["b"] = new[] { 3.0 } };
        public static IReadOnlyDictionary<string, IReadOnlyDictionary<DateTime, IReadOnlyList<double>>> NestedPrices()
            => new Dictionary<string, IReadOnlyDictionary<DateTime, IReadOnlyList<double>>>
            {
                ["a"] = new Dictionary<DateTime, IReadOnlyList<double>> { [new DateTime(2026, 1, 5)] = new List<double> { 1.0, 2.0 } },
            };
        public static Dictionary<string, Array> Frame()
            => new Dictionary<string, Array> { ["x"] = new[] { 1.0, 2.0 } };

        public static Tuple<int, double[], string> TupleResult() => Tuple.Create(1, new[] { 1.0, 2.0 }, "x");
        public static (string, IReadOnlyList<double>) ValueTupleResult() => ("x", new List<double> { 1.0 });
        public static KeyValuePair<string, IEnumerable<int>> PairResult() => new KeyValuePair<string, IEnumerable<int>>("k", new List<int> { 1 });
    }

    // Overloaded constructors with equal arity, objects in collections, a matrix argument and
    // interface-typed numeric results.
    public class Settings
    {
        public Settings(DateTime start, IEnumerable<DateTime> dates, int count, int factor, double scale)
        {
            Name = "default";
            Start = start;
            Dates = dates.ToList();
            Count = count;
            Factor = factor;
            Scale = scale;
        }

        public Settings(string name, int count, DateTime start, IEnumerable<Item> items, int factor)
        {
            Name = name;
            Count = count;
            Start = start;
            Dates = items.Select((p, i) => start.AddDays(i + 1)).ToList();
            Factor = factor;
        }

        public string Name { get; }
        public DateTime Start { get; }
        public IReadOnlyList<DateTime> Dates { get; }
        public int Count { get; }
        public int Factor { get; }
        public double Scale { get; }
    }

    public class ResultSet
    {
        private readonly Dictionary<string, Dictionary<DateTime, double[]>> _values;

        public ResultSet(Dictionary<string, Dictionary<DateTime, double[]>> values)
        {
            _values = values;
        }

        public IReadOnlyList<double> GetValues(string id, DateTime date) => _values[id][date];
    }

    public class Processor
    {
        public ResultSet Run(IReadOnlyList<Item> items, double[,] matrix, Settings settings)
        {
            if (matrix.GetLength(0) != items.Count || matrix.GetLength(1) != items.Count)
                throw new ArgumentException("Matrix must be items.Count x items.Count.");

            var values = new Dictionary<string, Dictionary<DateTime, double[]>>();
            for (var i = 0; i < items.Count; i++)
            {
                var byDate = new Dictionary<DateTime, double[]>();
                foreach (var date in settings.Dates)
                {
                    var row = new double[settings.Count];
                    for (var s = 0; s < row.Length; s++)
                        row[s] = items[i].Value * matrix[i, i] + s;
                    byDate[date] = row;
                }
                values[items[i].Id] = byDate;
            }
            return new ResultSet(values);
        }
    }
}
