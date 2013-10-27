#!/usr/bin/env python

"""A chat client that finds link-local users using RTP. Used to demonstrate
that this implementation of RTP is decoupled from EIGRP."""

import Tkinter
import tkMessageBox
import sys
from twisted.internet import tksupport

sys.path.append("..")

from tw_baseiptransport import reactor
import tw_baseiptransport
import rtp
import rtptlv
import util
import sysiface

# No reason for using this number other than I think it is unused elsewhere
PROTO_RTPCHAT = 0x0a00

class _BaseRTPChatGUI(object):
    """This is the base class for RTPChat graphical user interfaces. This
    serves as a programming inteface that should be overriden by the actual
    GUI class."""

    def __init__(self, sendfunc, quitfunc):
        """sendfunc -- The function that the GUI should call when the
                       GUI has text to send.
           quitfunc -- A function to call when a user quits the application"""
        self._send = sendfunc
        self._quit = quitfunc

    def lost_neigbor(self, neighbor):
        """Called when a neighbor has gone away."""

    def receive_text(self, neighbor, text):
        """Called when a neighbor has sent us a text message."""

    def update_username(self, neighbor, text):
        """Called when we receive a new username for a neighbor. (Including
        when we first discover a neighbor and obtain its username.)"""


class RTPChatTkinterGUI(_BaseRTPChatGUI):

    def __init__(self, *args, **kwargs):
        _BaseRTPChatGUI.__init__(self, *args, **kwargs)
        self._init_gui()
        self._neighbor_indexes = list()

    def _init_gui(self):
        self._root = Tkinter.Tk()
        tksupport.install(self._root)
        self._root.protocol("WM_DELETE_WINDOW", self._confirm_quit)
        self._root.title("RTPChat Tkinter GUI")
        self._root.geometry("575x685")

        self._frame_main = Tkinter.Frame(self._root)
        self._frame_main.grid()

        self._frame_messages = Tkinter.LabelFrame(self._frame_main,
                                                  text="Message Log")
        self._frame_messages.grid()
        self._txt_messages = Tkinter.Text(self._frame_messages)
        self._txt_messages.grid()
        self._txt_messages.config(state=Tkinter.DISABLED)

        self._frame_neighbors = Tkinter.LabelFrame(self._frame_main,
                                                   text="Neighbors List")
        self._frame_neighbors.grid()

        self._lst_neighbors = Tkinter.Listbox(self._frame_neighbors,
                                              selectmode=Tkinter.SINGLE)
        self._lst_neighbors.grid(row=1, column=1)

        self._frame_input = Tkinter.LabelFrame(self._frame_main,
                                               text="Input")
        self._frame_input.grid()
        self._var_input = Tkinter.StringVar()
        self._txt_input = Tkinter.Entry(self._frame_input,
                                        textvariable=self._var_input)
        self._txt_input.grid(row=2, column=1)

        self._btn_send = Tkinter.Button(self._frame_main, text="Send",
                                        command=self._send_text)
        self._btn_send.grid(row=3)

        self._btn_quit = Tkinter.Button(self._frame_main, text="Quit",
                                        command=self._confirm_quit)
        self._btn_quit.grid(row=4)
        self._write_local_msg("RTP Chat has started. Usage:")
        self._write_local_msg("When a neighbor RTP Chat client comes online, it will appear in the Neighbors list below.")
        self._write_local_msg("Click on a neighbor then type in the Input box to send them a message.")
        self._write_local_msg("Messages that you receive from neighbors will appear in this window.")
        self._write_local_msg("This is really only intended to test out RTP, so don't be surprised if RTP Chat does something bad.")

    def _write_local_msg(self, msg):
        """Write a message to self._txt_messages. Make _txt_messages writable
        only while we are using it, so it appears to be read-only to
        operators. Scroll the window down to the end."""
        self._txt_messages.config(state=Tkinter.NORMAL)
        self._txt_messages.insert(Tkinter.END, msg + "\n")
        self._txt_messages.config(state=Tkinter.DISABLED)
        self._txt_messages.yview_moveto(1)

    def _confirm_quit(self):
        if tkMessageBox.askokcancel("Quit", "Really quit?"):
            self._quit()

    def lost_neighbor(self, neighbor):
        self._write_local_msg("Lost neighbor with username " + \
                              neighbor._username)
        index = self._neighbor_indexes.index(neighbor)
        self._neighbor_indexes.remove(neighbor)
        self._lst_neighbors.delete(index, index)

    def _send_text(self):
        """Send the text that was entered in the input Entry widget to the
        selected neighbor, then clear the input Entry widget. Also
        make the message appear locally."""
        neighbor_index = self._lst_neighbors.index(Tkinter.ACTIVE)
        try:
            neighbor = self._neighbor_indexes[neighbor_index]
        except IndexError:
            self._write_local_msg("You must select a neighbor to talk to before sending a message.")
            return
            
        msg = self._var_input.get()
        self._send(neighbor, msg)
        self._write_local_msg("You told " + neighbor._username + ": \"" + \
                              msg + "\"")

        self._var_input.set('')

    def receive_text(self, neighbor, text):
        print text.text
        self._write_local_msg(neighbor._username + " tells you: \"" + text.text + "\"")

    def update_username(self, neighbor, username):
        # Keep track of which neighbor is at each index in the
        # neighbor listbox.
        self._write_local_msg("Updating username for neighbor " + str(neighbor) + " to " + username)
        self._lst_neighbors.insert(Tkinter.END, username)
        self._neighbor_indexes.append(neighbor)


class ValueText(rtptlv.ValueBase):
    """Plain text data."""

    FIELDS = [ "text" ]

    def __init__(self, *args, **kwargs):
        self.text = ""
        super(rtptlv.ValueBase, self).__thisclass__.__init__(self, *args,
                                                             **kwargs)

    def pack(self):
        return self.text

    def unpack(self, raw):
        return raw

    def _parse_kwargs(self, kwargs):
        self.text = self.unpack(kwargs["raw"])

    def _parse_args(self, args):
        if len(args) != 1:
            raise(ValueError("Exactly one arg is expected."))
        self.text = args[0]

    def getlen(self):
        return len(self.text)

    def __str__(self):
        return type(self).__name__ + "({} characters)".format(len(self.text))


class ValueEmpty(rtptlv.ValueBase):
    # ValueBase won't allow an empty TLV, so allow for that here.

    LEN = 0
    FIELDS = []

    def __init__(self, *args, **kwargs):
        pass

    def pack(self):
        return ""


class TLVText(rtptlv.TLVBase):
    TYPE   = PROTO_RTPCHAT | 1
    VALUES = [ ValueText ]


class TLVUserResponse(rtptlv.TLVBase):
    TYPE   = PROTO_RTPCHAT | 2
    VALUES = [ ValueText ]


class TLVUserRequest(rtptlv.TLVBase):
    TYPE   = PROTO_RTPCHAT | 3
    VALUES = [ ValueEmpty ]

    def __init__(self, *args, **kwargs):
        self.empty = ValueEmpty()
        self.type = self.TYPE


class RTPChat(rtp.ReliableTransportProtocol):

    """An example of an upper layer to RTP that is not EIGRP. Used to
    demonstrate that this implementation of RTP is decoupled from EIGRP."""

    # Supported UI options
    GTK_UI = 1

    def __init__(self, username, ui, ip, *args, **kwargs):
        rtp.ReliableTransportProtocol.__init__(self, *args, **kwargs)
        self.activate_iface(ip)
        if ui == self.GTK_UI:
            self._ui = RTPChatTkinterGUI(self._send_chat_msg,
                                         reactor.stop)
        else:
            raise(ValueError("Unsupported GUI type: {}".format(ui)))
        self._username = username
        self._tlvfactory.register_tlvs([TLVText,
                                        TLVUserRequest,
                                        TLVUserResponse])

    def _process_reply_tlvs(self, neighbor, hdr, tlvs):
        self.log.debug5("RTPCHAT processing reply TLV")
        for tlv in tlvs:
            if tlv.type == TLVText.TYPE:
                self.log.debug5("Receiving Text TLV.")
                self._process_chat_msg(neighbor, tlv.text)
            elif tlv.type == TLVUserResponse.TYPE:
                self.log.debug5("Receiving User Response TLV.")
                self._update_username(neighbor, tlv.text.text)
            else:
                self.log.debug("Unknown reply TLV: {}".format(tlv))

    def _update_username(self, neighbor, text):
        self.log.debug("Updating neighbor {} to use username " \
                       "{}".format(neighbor, text))
        neighbor._username = text
        self._ui.update_username(neighbor, text)

    def _process_chat_msg(self, neighbor, text):
        self._ui.receive_text(neighbor, text)

    def _send_username(self, neighbor):
        """Send our username to a neighbor."""
        tlvs = [TLVUserResponse(self._username)]
        self.log.debug5("Sending our username to neighbor {}...".format(neighbor))
        neighbor.send(self._rtphdr.OPC_REPLY, tlvs, True)

    def _process_request_tlvs(self, neighbor, hdr, tlvs):
        self.log.debug5("RTPCHAT processing request.")
        for tlv in tlvs:
            if tlv.type == TLVUserRequest.TYPE:
                self.log.debug5("Receiving User Request TLV.")
                self._send_username(neighbor)
            else:
                self.log.debug("Receiving unknown TLV type.")

    def _send_chat_msg(self, neighbor, text):
        tlvs = [TLVText(text)]
        neighbor.send(self._rtphdr.OPC_REPLY, tlvs, True)

    def initReceived(self, neighbor):
        pass

    def foundNeighbor(self, neighbor):
        self._request_username(neighbor)

    def _request_username(self, neighbor):
        tlvs = [TLVUserRequest()]
        self.log.debug5("Requesting username from neighbor {}".format(neighbor))
        neighbor.send(self._rtphdr.OPC_REQUEST, tlvs, True)

    def lostNeighbor(self, neighbor):
        self._ui.lost_neighbor(neighbor)

    def rtpReceived(self, neighbor, hdr, tlvs):
        self.log.debug5("RTPCHAT received a message...")
        if hdr.opcode == self._rtphdr.OPC_REPLY:
            self._process_reply_tlvs(neighbor, hdr, tlvs)
        elif hdr.opcode == self._rtphdr.OPC_REQUEST:
            self._process_request_tlvs(neighbor, hdr, tlvs)
        else:
            self.log.debug("Received unknown opcode: {}".format(hdr.opcode))

    def run(self):
        reactor.listenIP(88, self)
        self.log.info("RTPChat is starting...")
        reactor.run()


def main(args):
    if not util.is_admin():
        print("Must run as root/admin. Exiting.")
        return 1

    try:
        ip = args[1]
        user = args[2]
        logconfig = args[3]
    except:
        print("Usage: ./rtpchat.py ip user logconfig")
        return 1

    system = sysiface.SystemFactory(0, 0).build()
    rtpchat = RTPChat(user, RTPChat.GTK_UI, ip, system=system,
                      logconfig=logconfig)
    
    rtpchat.run()

if __name__ == "__main__":
    sys.exit(main(sys.argv))