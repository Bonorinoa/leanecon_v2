import re

with open("frontend/src/pages/EvalDashboard.jsx", "r") as f:
    content = f.read()

# Replace top imports
content = re.sub(
    r"^.*?const {[^}]+} = RechartsRuntime\n",
    """import React, { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  RadialBar,
  RadialBarChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";\n""",
    content,
    flags=re.DOTALL
)

# Remove window mount block
content = re.sub(
    r"if \(typeof window !== \"undefined\"\).*?export default EvalDashboard\n?",
    "export default EvalDashboard;\n",
    content,
    flags=re.DOTALL
)

with open("frontend/src/pages/EvalDashboard.jsx", "w") as f:
    f.write(content)
