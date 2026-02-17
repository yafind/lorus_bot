const tg = window.Telegram.WebApp;

tg.ready();
tg.expand();

tg.MainButton.setText("🍄 Профиль");
tg.MainButton.show();

const user = tg.initDataUnsafe?.user;
const userLine = document.getElementById("userLine");
const balanceLine = document.getElementById("balanceLine");
const statusLine = document.getElementById("statusLine");

if (user) {
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ");
  userLine.textContent = `Вы вошли как: ${fullName} (id: ${user.id})`;
} else {
  userLine.textContent = "Данные пользователя недоступны. Откройте Mini App через кнопку в боте.";
  balanceLine.textContent = "недоступен";
}

const loadBalance = () => {
  if (!user?.id) {
    statusLine.textContent = "Нет данных пользователя";
    return;
  }

  statusLine.textContent = "Обновляю баланс...";

  fetch(`/api/user-balance?user_id=${encodeURIComponent(user.id)}`)
    .then((response) => response.json())
    .then((payload) => {
      if (payload.ok) {
        balanceLine.textContent = `${payload.balance} 💎`;
        statusLine.textContent = "Готово к работе";
      } else {
        balanceLine.textContent = "ошибка";
        statusLine.textContent = "Ошибка загрузки баланса";
      }
    })
    .catch(() => {
      balanceLine.textContent = "ошибка";
      statusLine.textContent = "Ошибка загрузки баланса";
    });
};

loadBalance();

const sendCommand = (command) => {
  statusLine.textContent = "Отправляю команду в бота...";
  tg.sendData(JSON.stringify({ command }));
  tg.close();
};

tg.MainButton.onClick(() => sendCommand("profile"));

document.getElementById("openTasks").addEventListener("click", () => sendCommand("tasks"));
document.getElementById("openProfile").addEventListener("click", () => sendCommand("profile"));
document.getElementById("openMinigames").addEventListener("click", () => sendCommand("minigames"));
document.getElementById("openTopup").addEventListener("click", () => sendCommand("topup"));

document.querySelectorAll("[data-game]").forEach((button) => {
  button.addEventListener("click", () => {
    const game = button.getAttribute("data-game");
    sendCommand(`play_${game}`);
  });
});

fetch("/api/config")
  .then((response) => response.json())
  .then((config) => {
    const link = document.getElementById("paymentLink");
    if (config.payment_chat) {
      link.href = config.payment_chat;
    } else {
      link.style.display = "none";
    }
  })
  .catch(() => {
    const link = document.getElementById("paymentLink");
    link.style.display = "none";
  });
