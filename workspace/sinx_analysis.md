# 正弦函数 $\sin x$ 的性质分析

## 1. 定义 (Definition)

正弦函数可以通过多种等价方式定义：

- **单位圆定义**：在单位圆上，角度 $x$（弧度）对应的终边与单位圆的交点的纵坐标即为 $\sin x$。
- **级数定义 (Taylor 展开)**：

$$
\sin x = \sum_{n=0}^{\infty} (-1)^n \frac{x^{2n+1}}{(2n+1)!} = x - \frac{x^3}{3!} + \frac{x^5}{5!} - \frac{x^7}{7!} + \cdots
$$

- **Euler 公式**：

$$
\sin x = \frac{e^{ix} - e^{-ix}}{2i}
$$

---

## 2. 基本属性

| 属性 | 说明 |
|------|------|
| **定义域 (Domain)** | $(-\infty, +\infty)$，即全体实数 $\mathbb{R}$ |
| **值域 (Range)** | $[-1, 1]$ |
| **奇偶性** | **奇函数**：$\sin(-x) = -\sin x$ |
| **周期性 (Period)** | 最小正周期 $T = 2\pi$，即 $\sin(x + 2\pi) = \sin x$ |
| **有界性** | 有界，$|\sin x| \leq 1$ |
| **连续性** | 在 $\mathbb{R}$ 上处处连续 |
| **可导性** | 在 $\mathbb{R}$ 上无限次可导（光滑函数） |

---

## 3. 导数与积分

### 导数

$$
\frac{d}{dx} \sin x = \cos x
$$

$$
\frac{d^n}{dx^n} \sin x = \sin\!\left(x + \frac{n\pi}{2}\right)
$$

高阶导数以 4 为周期循环：
- $n=0$: $\sin x$
- $n=1$: $\cos x$
- $n=2$: $-\sin x$
- $n=3$: $-\cos x$
- $n=4$: $\sin x$

### 不定积分

$$
\int \sin x \, dx = -\cos x + C
$$

### 定积分（一个周期）

$$
\int_0^{2\pi} \sin x \, dx = 0
$$

---

## 4. 关键点

| $x$ (弧度) | $x$ (角度) | $\sin x$ |
|:----------:|:----------:|:--------:|
| $0$ | $0^\circ$ | $0$ |
| $\dfrac{\pi}{6}$ | $30^\circ$ | $\dfrac{1}{2}$ |
| $\dfrac{\pi}{4}$ | $45^\circ$ | $\dfrac{\sqrt{2}}{2}$ |
| $\dfrac{\pi}{3}$ | $60^\circ$ | $\dfrac{\sqrt{3}}{2}$ |
| $\dfrac{\pi}{2}$ | $90^\circ$ | $1$ |
| $\pi$ | $180^\circ$ | $0$ |
| $\dfrac{3\pi}{2}$ | $270^\circ$ | $-1$ |
| $2\pi$ | $360^\circ$ | $0$ |

---

## 5. 函数图像特征

```
  y
  ↑
1 +     ···              ···
  |    /   \            /   \
  |   /     \          /     \
0 +--/-------\--------/-------\----→ x
  | /         \      /         \
-1 +           \····/           \····
  |  0    π/2   π   3π/2  2π
```

- **振幅 (Amplitude)**：$A = 1$
- **零点 (Zeros)**：$x = k\pi,\ k \in \mathbb{Z}$
- **极大值点**：$x = \dfrac{\pi}{2} + 2k\pi$，最大值 $1$
- **极小值点**：$x = \dfrac{3\pi}{2} + 2k\pi$，最小值 $-1$
- **单调递增区间**：$\left[-\dfrac{\pi}{2}+2k\pi,\ \dfrac{\pi}{2}+2k\pi\right]$
- **单调递减区间**：$\left[\dfrac{\pi}{2}+2k\pi,\ \dfrac{3\pi}{2}+2k\pi\right]$

---

## 6. 重要恒等式

### 毕达哥拉斯恒等式

$$
\sin^2 x + \cos^2 x = 1
$$

### 和差公式

$$
\sin(x \pm y) = \sin x \cos y \pm \cos x \sin y
$$

### 倍角公式

$$
\sin(2x) = 2\sin x \cos x
$$

### 半角公式

$$
\sin^2\!\left(\frac{x}{2}\right) = \frac{1 - \cos x}{2}
$$

### 和差化积

$$
\sin A + \sin B = 2\sin\!\left(\frac{A+B}{2}\right)\cos\!\left(\frac{A-B}{2}\right)
$$

$$
\sin A - \sin B = 2\cos\!\left(\frac{A+B}{2}\right)\sin\!\left(\frac{A-B}{2}\right)
$$

### 积化和差

$$
\sin A \sin B = \frac{1}{2}[\cos(A-B) - \cos(A+B)]
$$

---

## 7. 极限与渐近行为

- $\displaystyle \lim_{x \to 0} \frac{\sin x}{x} = 1$ （重要极限）
- $\displaystyle \lim_{x \to 0} \frac{1 - \cos x}{x^2} = \frac{1}{2}$
- 当 $x \to 0$ 时，$\sin x \sim x$（等价无穷小）
- $\sin x$ 无水平渐近线，也无垂直渐近线

---

## 8. 与 Euler 公式的关系

由 Euler 公式 $e^{ix} = \cos x + i\sin x$ 可得：

$$
\sin x = \frac{e^{ix} - e^{-ix}}{2i}
$$

这建立了三角函数与复指数函数之间的桥梁，在复分析、信号处理中极为重要。

---

## 9. 总结

$\sin x$ 是数学中最基本、最重要的函数之一：

- 它是**周期函数**，周期为 $2\pi$，用于描述波动和振荡现象；
- 它是**奇函数**，图像关于原点对称；
- 它与 $\cos x$ 通过导数关系紧密相连：$\frac{d}{dx}\sin x = \cos x$；
- 它是 Fourier 分析的基础，任何周期函数都可展开为正弦/余弦级数；
- 它在物理学（简谐振动、波动）、工程学（信号处理、交流电路）、计算机图形学等领域有广泛应用。
