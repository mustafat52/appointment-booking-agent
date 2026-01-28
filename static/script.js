


async function sendMessage() {
    const input = document.getElementById("message");
    const chatBox = document.getElementById("chat-box");
    const text = input.value.trim();

    if (!text) return;

    // Show user message
    chatBox.innerHTML += `<p class="user"><b>You:</b> ${text}</p>`;
    chatBox.scrollTop = chatBox.scrollHeight;

    input.value = "";

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",

            },
            credentials:"include",
            body: JSON.stringify({
                
                message: text                
            }),
        });

        const data = await response.json();

        // Show bot reply
        chatBox.innerHTML += `<p class="bot"><b>Bot:</b> ${data.reply}</p>`;
        chatBox.scrollTop = chatBox.scrollHeight;

    } catch (error) {
        chatBox.innerHTML += `<p class="bot"><b>Bot:</b> ❌ Error connecting to server</p>`;
        console.error(error);
    }
}
