const tg = window.Telegram.WebApp;

tg.ready();
tg.expand();

const user = tg.initDataUnsafe?.user;
const userLine = document.getElementById("userLine");
const balanceLine = document.getElementById("balanceLine");
const resultLine = document.getElementById("resultLine");

if (user) {
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ");
  userLine.textContent = `Вы вошли как: ${fullName} (id: ${user.id})`;
} else {
  userLine.textContent = "Открой Mini App через кнопку бота";
  balanceLine.textContent = "недоступен";
  resultLine.textContent = "Нет данных пользователя";
}

const loadBalance = async () => {
  if (!user?.id) {
    return;
  }

  try {
    const response = await fetch(`/api/user-balance?user_id=${encodeURIComponent(user.id)}`);
    const payload = await response.json();

    if (payload.ok) {
      balanceLine.textContent = `${payload.balance} 💎`;
    } else {
      balanceLine.textContent = "ошибка";
    }
  } catch {
    balanceLine.textContent = "ошибка";
  }
};

loadBalance();

document.querySelectorAll("[data-game]").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!user?.id) {
      resultLine.textContent = "Ошибка: user_id недоступен";
      return;
    }

    resultLine.textContent = "Играем...";
    const game = button.getAttribute("data-game");

    try {
      const response = await fetch("/api/play", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          user_id: user.id,
          game
        })
      });

      const payload = await response.json();

      if (!response.ok || !payload.ok) {
        if (payload.error === "not_enough_balance") {
          balanceLine.textContent = `${payload.balance ?? 0} 💎`;
          resultLine.textContent = "Недостаточно алмазов для ставки";
          return;
        }

        resultLine.textContent = "Ошибка игры";
        return;
      }

      balanceLine.textContent = `${payload.balance} 💎`;
      if (payload.won) {
        resultLine.textContent = `${payload.game_name}: ${payload.value} — победа +${payload.reward} 💎`;
      } else {
        resultLine.textContent = `${payload.game_name}: ${payload.value} — проигрыш`;
      }
    } catch {
      resultLine.textContent = "Ошибка сети";
    }
  });
});

document.getElementById("refreshBalance").addEventListener("click", loadBalance);
